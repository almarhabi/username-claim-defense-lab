from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.database import LAB_PASSWORD
from app.main import create_app


def test_api_requires_synthetic_session_and_admin_key(settings: Settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/health").json() == {
            "status": "ok",
            "lab_only": True,
            "domain": "social.lab.internal",
        }
        assert client.post("/v1/usernames/lumen/claim").status_code == 401
        assert client.post("/v1/lab/reset").status_code == 403

        login = client.post(
            "/v1/auth/sessions", json={"username": "alice", "password": LAB_PASSWORD}
        )
        assert login.status_code == 201
        token = login.json()["session_token"]
        headers = {"Authorization": f"Bearer {token}"}
        claimed = client.post("/v1/usernames/lumen/claim", headers=headers)
        assert claimed.status_code == 200
        assert claimed.json()["owner"] == "alice"

        reset = client.post("/v1/lab/reset", headers={"X-Lab-Key": "test-admin-key"})
        assert reset.status_code == 200
        assert client.get("/v1/lab/metrics").json()["lab_only"] is True


def test_dashboard_is_served(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "social.lab.internal" in response.text
