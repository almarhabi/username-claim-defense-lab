from __future__ import annotations

import logging
import os
import threading
import time

import uvicorn

logger = logging.getLogger(__name__)


def runtime_port() -> int:
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError as exc:
        raise RuntimeError("PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("PORT must be between 1 and 65535")
    return port


def validate_runtime() -> None:
    for name in ("TELEGRAM_BOT_TOKEN", "LAB_ADMIN_KEY"):
        value = os.environ.get(name, "")
        if not value.strip():
            raise RuntimeError(f"{name} is required")
        if value != value.strip() or "\n" in value or "\r" in value:
            raise RuntimeError(f"{name} must be a non-empty single-line value")


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    validate_runtime()
    port = runtime_port()
    os.environ["LAB_API_URL"] = f"http://127.0.0.1:{port}"

    from app.main import app
    from bot.telegram_bot import run_bot

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=port,
            access_log=False,
            log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        )
    )
    server_thread = threading.Thread(target=server.run, name="synthetic-lab-api", daemon=True)
    server_thread.start()

    deadline = time.monotonic() + 30
    while not server.started:
        if not server_thread.is_alive():
            raise RuntimeError("The synthetic lab API stopped during startup")
        if time.monotonic() >= deadline:
            server.should_exit = True
            raise RuntimeError("Timed out while starting the synthetic lab API")
        time.sleep(0.1)

    logger.info("Synthetic API is ready; starting Telegram long polling")
    try:
        run_bot()
    finally:
        server.should_exit = True
        server_thread.join(timeout=10)
        if server_thread.is_alive():
            logger.warning("Synthetic API did not stop within the shutdown timeout")


if __name__ == "__main__":
    main()
