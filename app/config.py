from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Configuration for the local simulation; no external provider settings exist."""

    database_path: str
    admin_key: str
    cooldown_seconds: int = 14 * 24 * 60 * 60
    rate_limit_per_minute: int = 20
    session_ttl_seconds: int = 3600


def load_settings() -> Settings:
    data_dir = Path(os.getenv("LAB_DATA_DIR", ".lab-data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        database_path=os.getenv("LAB_DB_PATH", str(data_dir / "lab.db")),
        admin_key=os.getenv("LAB_ADMIN_KEY", "local-lab-admin-key"),
        cooldown_seconds=int(os.getenv("LAB_COOLDOWN_SECONDS", str(14 * 24 * 60 * 60))),
        rate_limit_per_minute=int(os.getenv("LAB_RATE_LIMIT", "20")),
        session_ttl_seconds=int(os.getenv("LAB_SESSION_TTL_SECONDS", "3600")),
    )
