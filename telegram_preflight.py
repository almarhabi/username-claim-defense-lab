from __future__ import annotations

import asyncio
import os

from telegram import Bot
from telegram.error import Conflict, TelegramError


async def verify() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    async with Bot(token) as bot:
        identity = await bot.get_me()
        print(f"Telegram authentication succeeded for @{identity.username}", flush=True)

        # Match run_polling's webhook cleanup without discarding queued updates.
        await bot.delete_webhook(drop_pending_updates=False)
        try:
            # getMe does not detect another polling consumer. This call does.
            # No offset is supplied, so a returned update is not acknowledged.
            await bot.get_updates(limit=1, timeout=0)
        except Conflict as exc:
            print(
                "::error::This Telegram token is already used by another getUpdates "
                "consumer. Stop the other bot/workflow or use a separate token.",
                flush=True,
            )
            raise SystemExit(2) from exc

    print("Telegram getUpdates preflight passed; no polling conflict detected", flush=True)


def main() -> None:
    try:
        asyncio.run(verify())
    except TelegramError as exc:
        print(
            f"::error::Telegram preflight failed ({type(exc).__name__}). "
            "Check the token and runner network access.",
            flush=True,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
