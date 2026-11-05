from __future__ import annotations

import pytest

from app.config import Settings
from app.database import Database
from app.service import LabService


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_path=str(tmp_path / "lab-test.db"),
        admin_key="test-admin-key",
        cooldown_seconds=3600,
        rate_limit_per_minute=5,
        session_ttl_seconds=3600,
    )


@pytest.fixture
def service(settings: Settings) -> LabService:
    return LabService(Database(settings.database_path), settings)
