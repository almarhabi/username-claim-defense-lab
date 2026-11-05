from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from bot.telegram_bot import LabTelegramBot


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any], bool, str]] = []

    async def post(
        self,
        path: str,
        payload: dict[str, Any],
        admin: bool = True,
        session_token: str = "",
    ) -> dict[str, Any]:
        self.calls.append(("POST", path, payload, admin, session_token))
        if path == "/v1/auth/sessions":
            return {
                "session_token": "synthetic-secret-token",
                "account": payload["username"],
                "expires_at": "2030-01-01T00:00:00+00:00",
            }
        return {"status": "ok"}


def make_update(user_id: int | None) -> tuple[SimpleNamespace, AsyncMock]:
    reply = AsyncMock()
    return (
        SimpleNamespace(
            effective_user=SimpleNamespace(id=user_id) if user_id is not None else None,
            effective_message=SimpleNamespace(reply_text=reply),
        ),
        reply,
    )


@pytest.mark.asyncio
async def test_session_token_is_stored_but_never_sent_to_telegram() -> None:
    client = FakeClient()
    bot = LabTelegramBot(client, {123})
    update, reply = make_update(123)

    await bot.session(update, SimpleNamespace(args=["alice"]))
    output = "\n".join(str(call.args[0]) for call in reply.await_args_list)
    assert "synthetic-secret-token" not in output
    assert '"account": "alice"' in output

    reply.reset_mock()
    await bot.claim(update, SimpleNamespace(args=["lumen"]))
    assert client.calls[-1] == (
        "POST",
        "/v1/usernames/lumen/claim",
        {},
        False,
        "synthetic-secret-token",
    )


@pytest.mark.asyncio
async def test_sessions_are_isolated_between_allow_listed_users() -> None:
    client = FakeClient()
    bot = LabTelegramBot(client, {123, 456})
    first, _ = make_update(123)
    second, second_reply = make_update(456)

    await bot.session(first, SimpleNamespace(args=["alice"]))
    await bot.whoami(second, SimpleNamespace())

    output = second_reply.await_args.args[0]
    assert '"synthetic_session": false' in output
    assert "alice" not in output


@pytest.mark.asyncio
async def test_unauthorized_user_cannot_call_the_lab() -> None:
    client = FakeClient()
    bot = LabTelegramBot(client, {123})
    update, reply = make_update(999)

    await bot.names(update, SimpleNamespace())
    assert client.calls == []
    assert "غير مصرح" in reply.await_args.args[0]


@pytest.mark.asyncio
async def test_claim_without_session_fails_before_http_request() -> None:
    client = FakeClient()
    bot = LabTelegramBot(client, {123})
    update, reply = make_update(123)

    await bot.claim(update, SimpleNamespace(args=["lumen"]))
    assert client.calls == []
    assert "/session ACCOUNT" in reply.await_args.args[0]
