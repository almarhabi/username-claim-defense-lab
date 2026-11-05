from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


LAB_PASSWORD = "lab-only-password"
ACCOUNT_NAMES = (
    "alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi",
    "ivan", "judy", "ken", "laura", "mallory", "nancy", "oscar", "peggy",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    salt_hex, expected = encoded.split("$", 1)
    actual = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(actual.hex(), expected)


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        if self.path != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usernames (
                    name TEXT PRIMARY KEY,
                    owner_account_id INTEGER REFERENCES accounts(id),
                    available_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS rate_limits (
                    key TEXT NOT NULL,
                    window_start INTEGER NOT NULL,
                    request_count INTEGER NOT NULL,
                    PRIMARY KEY (key, window_start)
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT,
                    outcome TEXT NOT NULL,
                    details TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC);
                """
            )
            count = db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            if count == 0:
                self._seed(db)

    def _seed(self, db: sqlite3.Connection) -> None:
        now = utc_now()
        for name in ACCOUNT_NAMES:
            salt = secrets.token_bytes(16)
            db.execute(
                "INSERT INTO accounts(username, password_hash, created_at) VALUES (?, ?, ?)",
                (name, hash_password(LAB_PASSWORD, salt), iso(now - timedelta(days=400))),
            )
        ids = {
            row["username"]: row["id"]
            for row in db.execute("SELECT id, username FROM accounts")
        }
        names = (
            ("rare", None, now),
            ("nova", ids["alice"], now),
            ("pixel", ids["bob"], now),
            ("lumen", None, now - timedelta(seconds=1)),
            ("orbit", ids["carol"], now),
        )
        for name, owner, available_at in names:
            db.execute(
                "INSERT INTO usernames(name, owner_account_id, available_at) VALUES (?, ?, ?)",
                (name, owner, iso(available_at)),
            )
        db.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES ('defenses_enabled', 'true')"
        )
        self.audit(db, "lab.seeded", None, "ok", {"accounts": len(ACCOUNT_NAMES)})

    def reset(self) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for table in ("sessions", "rate_limits", "usernames", "accounts", "audit_events", "settings"):
                db.execute(f"DELETE FROM {table}")
            self._seed(db)
            db.execute("COMMIT")

    @staticmethod
    def audit(
        db: sqlite3.Connection,
        event_type: str,
        actor: str | None,
        outcome: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        db.execute(
            "INSERT INTO audit_events(created_at, event_type, actor, outcome, details) VALUES (?, ?, ?, ?, ?)",
            (iso(utc_now()), event_type, actor, outcome, json.dumps(details or {}, sort_keys=True)),
        )
