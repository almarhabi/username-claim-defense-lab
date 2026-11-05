from __future__ import annotations

import httpx
import pytest

from bot.lab_client import LabClient


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://social.lab.internal.evil.example",
        "http://user:password@social:8000",
        "http://social:8000/redirect",
        "http://social:8000?target=elsewhere",
    ],
)
def test_client_rejects_non_lab_destinations(url: str) -> None:
    with pytest.raises(ValueError):
        LabClient(url, "test-key")


@pytest.mark.asyncio
async def test_client_accepts_pinned_lab_url() -> None:
    client = LabClient("http://social.lab.internal:8000", "test-key")
    await client.close()


@pytest.mark.asyncio
async def test_client_separates_session_and_admin_credentials() -> None:
    client = LabClient("http://social:8000", "admin-secret")
    with pytest.raises(ValueError):
        await client.post("/v1/example", {}, admin=True, session_token="lab-session")
    await client.close()


@pytest.mark.asyncio
async def test_session_request_does_not_include_admin_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer synthetic-session"
        assert "X-Lab-Key" not in request.headers
        return httpx.Response(200, json={"status": "ok"})

    client = LabClient("http://social:8000", "admin-secret")
    await client.close()
    client._client = httpx.AsyncClient(
        base_url="http://social:8000",
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    result = await client.post(
        "/v1/usernames/lumen/claim", {}, admin=False, session_token="synthetic-session"
    )
    assert result == {"status": "ok"}
    await client.close()
