from __future__ import annotations

import json
import re
import secrets
import sqlite3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from .config import Settings
from .database import Database, iso, parse_time, utc_now, verify_password


NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,19}$")


class LabError(ValueError):
    pass


class LabService:
    def __init__(self, database: Database, settings: Settings):
        self.db = database
        self.settings = settings

    @staticmethod
    def validate_name(name: str) -> str:
        if not NAME_PATTERN.fullmatch(name):
            raise LabError("Names must match ^[a-z][a-z0-9_]{2,19}$")
        return name

    @staticmethod
    def _account_id(db: sqlite3.Connection, username: str) -> int:
        row = db.execute("SELECT id FROM accounts WHERE username = ?", (username,)).fetchone()
        if row is None:
            raise LabError(f"Unknown synthetic account: {username}")
        return int(row["id"])

    def create_session(self, username: str, password: str) -> dict[str, Any] | None:
        with self.db.connect() as db:
            row = db.execute(
                "SELECT id, password_hash FROM accounts WHERE username = ?", (username,)
            ).fetchone()
            if row is None or not verify_password(password, row["password_hash"]):
                self.db.audit(db, "session.created", username, "denied")
                return None
            token = secrets.token_urlsafe(32)
            expires_at = utc_now() + timedelta(seconds=self.settings.session_ttl_seconds)
            db.execute(
                "INSERT INTO sessions(token, account_id, expires_at) VALUES (?, ?, ?)",
                (token, row["id"], iso(expires_at)),
            )
            self.db.audit(db, "session.created", username, "ok", {"expires_at": iso(expires_at)})
            return {"session_token": token, "account": username, "expires_at": iso(expires_at)}

    def authenticate(self, token: str) -> str | None:
        with self.db.connect() as db:
            row = db.execute(
                """
                SELECT a.username, s.expires_at FROM sessions s
                JOIN accounts a ON a.id = s.account_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
            if row is None or parse_time(row["expires_at"]) <= utc_now():
                return None
            return str(row["username"])

    def revoke_session(self, token: str) -> None:
        with self.db.connect() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def defenses_enabled(self) -> bool:
        with self.db.connect() as db:
            row = db.execute(
                "SELECT value FROM settings WHERE key = 'defenses_enabled'"
            ).fetchone()
            return row is None or row["value"] == "true"

    def set_defenses(self, enabled: bool) -> dict[str, Any]:
        with self.db.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES ('defenses_enabled', ?)",
                ("true" if enabled else "false",),
            )
            self.db.audit(db, "defenses.changed", "lab-admin", "ok", {"enabled": enabled})
        return {"defenses_enabled": enabled}

    def _is_rate_limited(self, db: sqlite3.Connection, actor: str, now: Any) -> bool:
        if not self.defenses_enabled():
            return False
        window = int(now.timestamp() // 60)
        db.execute(
            """
            INSERT INTO rate_limits(key, window_start, request_count) VALUES (?, ?, 1)
            ON CONFLICT(key, window_start)
            DO UPDATE SET request_count = request_count + 1
            """,
            (actor, window),
        )
        count = db.execute(
            "SELECT request_count FROM rate_limits WHERE key = ? AND window_start = ?",
            (actor, window),
        ).fetchone()[0]
        return count > self.settings.rate_limit_per_minute

    def claim(self, name: str, actor: str, source: str = "api") -> dict[str, Any]:
        self.validate_name(name)
        self._validate_actor(actor)
        now = utc_now()
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            account_id = self._account_id(db, actor)
            db.execute(
                "INSERT OR IGNORE INTO usernames(name, available_at) VALUES (?, ?)",
                (name, iso(now)),
            )
            if self._is_rate_limited(db, actor, now):
                self.db.audit(db, "username.claim", actor, "rate_limited", {"name": name, "source": source})
                db.execute("COMMIT")
                return {"status": "rate_limited", "name": name, "actor": actor}
            row = db.execute("SELECT * FROM usernames WHERE name = ?", (name,)).fetchone()
            if row["owner_account_id"] is not None:
                owner = db.execute(
                    "SELECT username FROM accounts WHERE id = ?", (row["owner_account_id"],)
                ).fetchone()[0]
                self.db.audit(db, "username.claim", actor, "taken", {"name": name, "owner": owner})
                db.execute("COMMIT")
                return {"status": "taken", "name": name, "owner": owner}
            available_at = parse_time(row["available_at"])
            if self.defenses_enabled() and available_at > now:
                self.db.audit(
                    db, "username.claim", actor, "cooldown",
                    {"name": name, "available_at": row["available_at"]},
                )
                db.execute("COMMIT")
                return {"status": "cooldown", "name": name, "available_at": row["available_at"]}
            db.execute(
                """
                UPDATE usernames
                SET owner_account_id = ?, version = version + 1
                WHERE name = ? AND owner_account_id IS NULL AND version = ?
                """,
                (account_id, name, row["version"]),
            )
            self.db.audit(db, "username.claim", actor, "claimed", {"name": name, "source": source})
            db.execute("COMMIT")
            return {"status": "claimed", "name": name, "owner": actor, "version": row["version"] + 1}

    def release(self, name: str, actor: str) -> dict[str, Any]:
        self.validate_name(name)
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            account_id = self._account_id(db, actor)
            row = db.execute("SELECT * FROM usernames WHERE name = ?", (name,)).fetchone()
            if row is None or row["owner_account_id"] != account_id:
                raise LabError("Only the current owner can release this name")
            available_at = utc_now() + timedelta(seconds=self.settings.cooldown_seconds)
            db.execute(
                """
                UPDATE usernames SET owner_account_id = NULL, available_at = ?, version = version + 1
                WHERE name = ?
                """,
                (iso(available_at), name),
            )
            self.db.audit(
                db, "username.released", actor, "ok",
                {"name": name, "available_at": iso(available_at)},
            )
            db.execute("COMMIT")
            return {"status": "released", "name": name, "available_at": iso(available_at)}

    def transfer(self, name: str, source: str, target: str) -> dict[str, Any]:
        self.validate_name(name)
        self._validate_actor(source)
        self._validate_actor(target)
        if source == target:
            raise LabError("Source and target accounts must differ")
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            source_id = self._account_id(db, source)
            target_id = self._account_id(db, target)
            row = db.execute("SELECT * FROM usernames WHERE name = ?", (name,)).fetchone()
            if row is None or row["owner_account_id"] != source_id:
                raise LabError(f"{source} does not own {name}")
            cursor = db.execute(
                """
                UPDATE usernames SET owner_account_id = ?, version = version + 1
                WHERE name = ? AND owner_account_id = ? AND version = ?
                """,
                (target_id, name, source_id, row["version"]),
            )
            if cursor.rowcount != 1:
                raise LabError("Name changed during transfer; retry with fresh state")
            self.db.audit(
                db, "username.transferred", source, "ok",
                {"name": name, "target": target, "version": row["version"] + 1},
            )
            db.execute("COMMIT")
            return {
                "status": "transferred", "name": name, "source": source,
                "target": target, "version": row["version"] + 1,
                "availability_gap": False,
            }

    def _prepare_available_name(self, name: str) -> None:
        self.validate_name(name)
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                INSERT INTO usernames(name, owner_account_id, available_at) VALUES (?, NULL, ?)
                ON CONFLICT(name) DO UPDATE SET owner_account_id = NULL, available_at = excluded.available_at
                """,
                (name, iso(utc_now())),
            )
            db.execute("DELETE FROM rate_limits")
            self.db.audit(db, "scenario.prepared", "lab-admin", "ok", {"name": name})
            db.execute("COMMIT")

    def simulate_race(self, name: str, contenders: int) -> dict[str, Any]:
        if not 2 <= contenders <= 16:
            raise LabError("Contenders must be between 2 and 16")
        from .database import ACCOUNT_NAMES

        self._prepare_available_name(name)
        actors = list(ACCOUNT_NAMES[:contenders])
        with ThreadPoolExecutor(max_workers=contenders) as pool:
            results = list(pool.map(lambda actor: self.claim(name, actor, "race"), actors))
        winners = [result["owner"] for result in results if result["status"] == "claimed"]
        return {
            "scenario": "race", "name": name, "contenders": contenders,
            "winner": winners[0] if winners else None,
            "successful_claims": len(winners), "invariant_preserved": len(winners) == 1,
            "outcomes": dict(Counter(result["status"] for result in results)),
            "results": results,
        }

    def simulate_burst(self, actor: str, requests: int, name: str = "burst") -> dict[str, Any]:
        self._validate_actor(actor)
        if not 1 <= requests <= 500:
            raise LabError("Requests must be between 1 and 500")
        self._prepare_available_name(name)
        results = [self.claim(name, actor, "burst") for _ in range(requests)]
        outcomes = Counter(result["status"] for result in results)
        return {
            "scenario": "burst", "actor": actor, "name": name, "requests": requests,
            "defenses_enabled": self.defenses_enabled(),
            "rate_limit_per_minute": self.settings.rate_limit_per_minute,
            "outcomes": dict(outcomes),
            "detection_effective": outcomes.get("rate_limited", 0) > 0 if self.defenses_enabled() else None,
        }

    def list_accounts(self) -> list[dict[str, Any]]:
        with self.db.connect() as db:
            return [
                {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}
                for row in db.execute("SELECT * FROM accounts ORDER BY id")
            ]

    def list_usernames(self) -> list[dict[str, Any]]:
        with self.db.connect() as db:
            rows = db.execute(
                """
                SELECT u.name, u.available_at, u.version, a.username AS owner
                FROM usernames u LEFT JOIN accounts a ON a.id = u.owner_account_id
                ORDER BY u.name
                """
            )
            return [dict(row) for row in rows]

    def audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self.db.connect() as db:
            rows = db.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            events = []
            for row in rows:
                event = dict(row)
                event["details"] = json.loads(event["details"])
                events.append(event)
            return events

    def metrics(self) -> dict[str, Any]:
        with self.db.connect() as db:
            outcomes = {
                row["outcome"]: row["count"]
                for row in db.execute(
                    "SELECT outcome, COUNT(*) AS count FROM audit_events GROUP BY outcome"
                )
            }
            return {
                "lab_only": True,
                "domain": "social.lab.internal",
                "accounts": db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0],
                "active_sessions": db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
                "defenses_enabled": self.defenses_enabled(),
                "cooldown_seconds": self.settings.cooldown_seconds,
                "rate_limit_per_minute": self.settings.rate_limit_per_minute,
                "outcomes": outcomes,
            }

    def _validate_actor(self, actor: str) -> None:
        self.validate_name(actor)
        with self.db.connect() as db:
            self._account_id(db, actor)
