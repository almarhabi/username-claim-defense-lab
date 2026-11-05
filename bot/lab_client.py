from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx


class LabClient:
    """HTTP client pinned to the synthetic lab network.

    Redirects are disabled and credentials in URLs are rejected. Telegram users
    cannot select a destination host or an arbitrary request path.
    """

    ALLOWED_HOSTS = {"social", "social.lab.internal", "localhost", "127.0.0.1"}

    def __init__(self, base_url: str, admin_key: str):
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in self.ALLOWED_HOSTS
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("LAB_API_URL must identify only the isolated synthetic lab service")
        if not admin_key:
            raise ValueError("LAB_ADMIN_KEY must not be empty")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=30, follow_redirects=False
        )
        self._headers = {"X-Lab-Key": admin_key}

    async def get(self, path: str, admin: bool = False) -> Any:
        response = await self._client.get(path, headers=self._headers if admin else None)
        response.raise_for_status()
        return response.json()

    async def post(self, path: str, payload: dict[str, Any], admin: bool = True) -> Any:
        response = await self._client.post(
            path, json=payload, headers=self._headers if admin else None
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()
