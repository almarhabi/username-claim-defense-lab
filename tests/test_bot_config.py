from __future__ import annotations

import pytest

from bot.lab_client import LabClient
from bot.telegram_bot import parse_allowed_users


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


def test_telegram_allow_list_is_fail_closed() -> None:
    assert parse_allowed_users("123, 456") == {123, 456}
    for raw in ("", "abc", "123,-4"):
        with pytest.raises(ValueError):
            parse_allowed_users(raw)
