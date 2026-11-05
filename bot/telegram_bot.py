from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .lab_client import LabClient

logger = logging.getLogger(__name__)


class LabTelegramBot:
    """Telegram controller for the synthetic service only.

    Access is intentionally unrestricted. Anyone who can find the bot can operate
    the lab, including resetting it. Sessions remain isolated by Telegram user ID.
    """

    HELP = (
        "مختبر أسماء المستخدمين الاصطناعية\n\n"
        "الحالة والاستعلام:\n"
        "/status — فحص الخادم ومقاييسه\n"
        "/names — الأسماء ومالكوها\n"
        "/accounts — الحسابات الاصطناعية\n\n"
        "جلسة المختبر الخاصة بك:\n"
        "/session ACCOUNT — إنشاء جلسة اصطناعية\n"
        "/whoami — الحساب المرتبط بجلستك\n"
        "/logout — إبطال الجلسة\n"
        "/claim NAME — التقاط اسم باستخدام جلستك\n"
        "/release NAME — تحرير اسم تملكه جلستك\n"
        "/mytransfer NAME TARGET — نقل اسم تملكه جلستك\n\n"
        "إدارة سيناريوهات المختبر:\n"
        "/race NAME [2-16] — تجربة سباق الالتقاط\n"
        "/burst ACCOUNT REQUESTS [NAME] — تجربة محدد الطلبات\n"
        "/transfer NAME SOURCE TARGET — نقل إداري داخل المختبر\n"
        "/defenses on|off — تشغيل الدفاعات أو تعطيلها\n"
        "/audit [1-100] — آخر أحداث التدقيق\n"
        "/reset CONFIRM — إعادة جميع بيانات المختبر\n\n"
        "كل البيانات اصطناعية. البوت مفتوح لكل مستخدمي Telegram."
    )

    COMMANDS = [
        BotCommand("help", "عرض الأوامر"),
        BotCommand("status", "حالة المختبر"),
        BotCommand("names", "عرض الأسماء"),
        BotCommand("accounts", "عرض الحسابات الاصطناعية"),
        BotCommand("session", "إنشاء جلسة اصطناعية"),
        BotCommand("whoami", "عرض الجلسة الحالية"),
        BotCommand("logout", "إبطال الجلسة"),
        BotCommand("claim", "التقاط اسم"),
        BotCommand("release", "تحرير اسم"),
        BotCommand("mytransfer", "نقل اسم باستخدام الجلسة"),
        BotCommand("race", "تشغيل سباق التقاط"),
        BotCommand("burst", "تشغيل اختبار معدل الطلبات"),
        BotCommand("transfer", "نقل إداري داخل المختبر"),
        BotCommand("defenses", "تغيير حالة الدفاعات"),
        BotCommand("audit", "عرض سجل التدقيق"),
        BotCommand("reset", "إعادة ضبط المختبر"),
    ]

    def __init__(
        self,
        client: LabClient,
        fixture_password: str = "lab-only-password",
        state_path: Path | None = None,
    ):
        if not fixture_password:
            raise ValueError("The synthetic fixture password must not be empty")
        self.client = client
        self.fixture_password = fixture_password
        self.state_path = state_path
        self._sessions: dict[int, dict[str, str]] = {}
        self._load_sessions()

    def _load_sessions(self) -> None:
        if self.state_path is None:
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("session state must be an object")
            sessions: dict[int, dict[str, str]] = {}
            for raw_user_id, record in raw.items():
                if not isinstance(record, dict):
                    raise ValueError("invalid session record")
                user_id = int(raw_user_id)
                values = {key: record[key] for key in ("token", "account", "expires_at")}
                if not all(isinstance(value, str) and value for value in values.values()):
                    raise ValueError("invalid session values")
                sessions[user_id] = values
            self._sessions = sessions
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring invalid synthetic Telegram session state: %s", exc)

    def _save_sessions(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        payload = {str(user_id): record for user_id, record in self._sessions.items()}
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.state_path)

    async def _authorized(self, update: Update) -> bool:
        if update.effective_user is not None:
            return True
        if update.effective_message:
            await update.effective_message.reply_text("تعذر تحديد مستخدم Telegram.")
        return False

    @staticmethod
    async def _send_json(update: Update, value: Any) -> None:
        text = json.dumps(value, ensure_ascii=False, indent=2)
        if len(text) > 3500:
            text = text[:3500] + "\n… output truncated …"
        if update.effective_message:
            await update.effective_message.reply_text(text)

    async def _execute(
        self, update: Update, operation: Callable[[], Awaitable[Any]]
    ) -> None:
        if not await self._authorized(update):
            return
        try:
            await self._send_json(update, await operation())
        except httpx.HTTPStatusError as exc:
            try:
                detail: Any = exc.response.json()
            except ValueError:
                detail = {"error": "The lab rejected the request"}
            await self._send_json(update, detail)
        except httpx.HTTPError:
            logger.exception("Synthetic lab request failed")
            await self._send_json(update, {"error": "تعذر الوصول إلى خادم المختبر المحلي"})

    async def _execute_with_session(
        self, update: Update, operation: Callable[[str], Awaitable[Any]]
    ) -> None:
        user = update.effective_user
        record = self._sessions.get(user.id) if user is not None else None
        if record is None:
            await self._send_json(
                update, {"error": "أنشئ جلسة اصطناعية أولاً باستخدام /session ACCOUNT"}
            )
            return
        await self._execute(update, lambda: operation(record["token"]))

    async def help(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._authorized(update) and update.effective_message:
            await update.effective_message.reply_text(self.HELP)

    async def status(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        async def read_status() -> dict[str, Any]:
            return {
                "health": await self.client.get("/health"),
                "metrics": await self.client.get("/v1/lab/metrics"),
            }

        await self._execute(update, read_status)

    async def names(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await self._execute(update, lambda: self.client.get("/v1/usernames"))

    async def accounts(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await self._execute(update, lambda: self.client.get("/v1/accounts"))

    async def session(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if len(context.args) != 1:
            await self._send_json(update, {"usage": "/session ACCOUNT"})
            return
        user_id = update.effective_user.id
        account = context.args[0]

        async def create_session() -> dict[str, Any]:
            result = await self.client.post(
                "/v1/auth/sessions",
                {"username": account, "password": self.fixture_password},
                admin=False,
            )
            self._sessions[user_id] = {
                "token": result["session_token"],
                "account": result["account"],
                "expires_at": result["expires_at"],
            }
            self._save_sessions()
            return {
                "status": "synthetic_session_created",
                "account": result["account"],
                "expires_at": result["expires_at"],
            }

        await self._execute(update, create_session)

    async def whoami(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        record = self._sessions.get(update.effective_user.id)
        if record is None:
            result = {"synthetic_session": False}
        else:
            result = {
                "synthetic_session": True,
                "account": record["account"],
                "expires_at": record["expires_at"],
            }
        await self._send_json(update, result)

    async def logout(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        user_id = update.effective_user.id

        async def revoke(token: str) -> dict[str, str]:
            await self.client.delete("/v1/auth/sessions", session_token=token)
            self._sessions.pop(user_id, None)
            self._save_sessions()
            return {"status": "synthetic_session_revoked"}

        await self._execute_with_session(update, revoke)

    async def claim(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if len(context.args) != 1:
            await self._send_json(update, {"usage": "/claim NAME"})
            return
        name = context.args[0]
        await self._execute_with_session(
            update,
            lambda token: self.client.post(
                f"/v1/usernames/{name}/claim", {}, admin=False, session_token=token
            ),
        )

    async def release(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if len(context.args) != 1:
            await self._send_json(update, {"usage": "/release NAME"})
            return
        name = context.args[0]
        await self._execute_with_session(
            update,
            lambda token: self.client.post(
                f"/v1/usernames/{name}/release", {}, admin=False, session_token=token
            ),
        )

    async def mytransfer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if len(context.args) != 2:
            await self._send_json(update, {"usage": "/mytransfer NAME TARGET"})
            return
        name, target = context.args
        await self._execute_with_session(
            update,
            lambda token: self.client.post(
                f"/v1/usernames/{name}/transfer",
                {"target_account": target},
                admin=False,
                session_token=token,
            ),
        )

    async def race(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if not 1 <= len(context.args) <= 2:
            await self._send_json(update, {"usage": "/race NAME [2-16]"})
            return
        try:
            contenders = int(context.args[1]) if len(context.args) == 2 else 8
        except ValueError:
            await self._send_json(update, {"error": "عدد المتنافسين يجب أن يكون رقماً"})
            return
        await self._execute(
            update,
            lambda: self.client.post(
                "/v1/lab/race", {"name": context.args[0], "contenders": contenders}
            ),
        )

    async def burst(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if not 2 <= len(context.args) <= 3:
            await self._send_json(update, {"usage": "/burst ACCOUNT REQUESTS [NAME]"})
            return
        try:
            requests = int(context.args[1])
        except ValueError:
            await self._send_json(update, {"error": "عدد الطلبات يجب أن يكون رقماً"})
            return
        payload = {
            "account": context.args[0],
            "requests": requests,
            "name": context.args[2] if len(context.args) == 3 else "burst",
        }
        await self._execute(update, lambda: self.client.post("/v1/lab/burst", payload))

    async def transfer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if len(context.args) != 3:
            await self._send_json(update, {"usage": "/transfer NAME SOURCE TARGET"})
            return
        payload = {
            "name": context.args[0],
            "source": context.args[1],
            "target": context.args[2],
        }
        await self._execute(update, lambda: self.client.post("/v1/lab/transfer", payload))

    async def defenses(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if len(context.args) != 1 or context.args[0].lower() not in {"on", "off"}:
            await self._send_json(update, {"usage": "/defenses on|off"})
            return
        enabled = context.args[0].lower() == "on"
        await self._execute(
            update, lambda: self.client.post("/v1/lab/defenses", {"enabled": enabled})
        )

    async def audit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        try:
            limit = int(context.args[0]) if context.args else 20
            if not 1 <= limit <= 100:
                raise ValueError
        except ValueError:
            await self._send_json(update, {"usage": "/audit [1-100]"})
            return
        await self._execute(
            update, lambda: self.client.get(f"/v1/lab/audit?limit={limit}", True)
        )

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if context.args != ["CONFIRM"]:
            await self._send_json(update, {"usage": "/reset CONFIRM"})
            return

        async def reset_lab() -> dict[str, Any]:
            result = await self.client.post("/v1/lab/reset", {})
            self._sessions.clear()
            self._save_sessions()
            return result

        await self._execute(update, reset_lab)


def run_bot() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    port = int(os.environ.get("PORT", "8000"))
    client = LabClient(
        os.environ.get("LAB_API_URL", f"http://127.0.0.1:{port}"),
        os.environ.get("LAB_ADMIN_KEY", ""),
    )
    data_dir = Path(os.environ.get("LAB_DATA_DIR", ".lab-data"))
    bot = LabTelegramBot(
        client,
        os.environ.get("LAB_FIXTURE_PASSWORD", "lab-only-password"),
        state_path=data_dir / "telegram-sessions.json",
    )

    async def configure_commands(application: Application) -> None:
        await application.bot.set_my_commands(bot.COMMANDS)

    async def close_client(_: Application) -> None:
        await client.close()

    async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Telegram handler failed for update %s", update, exc_info=context.error)

    application = (
        Application.builder()
        .token(token)
        .post_init(configure_commands)
        .post_shutdown(close_client)
        .build()
    )
    for command, handler in {
        "start": bot.help,
        "help": bot.help,
        "status": bot.status,
        "names": bot.names,
        "accounts": bot.accounts,
        "session": bot.session,
        "whoami": bot.whoami,
        "logout": bot.logout,
        "claim": bot.claim,
        "release": bot.release,
        "mytransfer": bot.mytransfer,
        "race": bot.race,
        "burst": bot.burst,
        "transfer": bot.transfer,
        "defenses": bot.defenses,
        "audit": bot.audit,
        "reset": bot.reset,
    }.items():
        application.add_handler(CommandHandler(command, handler))
    application.add_error_handler(on_error)
    # Keep Telegram's unconfirmed updates queued during the short restart gap.
    application.run_polling(allowed_updates=["message"], drop_pending_updates=False)
