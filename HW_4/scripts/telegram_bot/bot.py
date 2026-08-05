from __future__ import annotations

import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from config.settings import load_settings
from scripts.rag.service import RagAnswerService
from scripts.telegram_bot.handlers import (
    help_command,
    provider_command,
    question_handler,
    reset_command,
    sources_command,
    start_command,
    status_command,
    unknown_command,
)
from scripts.telegram_bot.rate_limit import BotRateLimiter


def build_application():
    settings = load_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN не налаштовано в ENV/.env/constants.py"
        )

    timeout = settings.telegram_network_timeout_seconds
    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .connect_timeout(timeout)
        .read_timeout(timeout)
        .write_timeout(timeout)
        .pool_timeout(timeout)
        .build()
    )
    application.bot_data["rag_service"] = RagAnswerService(
        settings=settings
    )
    application.bot_data["rate_limiter"] = BotRateLimiter(
        state_path=PROJECT_ROOT / "local_state" / "bot_usage.json",
        per_user_limit=settings.per_user_request_limit,
        window_seconds=settings.per_user_window_seconds,
        openai_daily_limit=settings.openai_daily_request_limit,
        freemodel_daily_limit=settings.freemodel_daily_request_limit,
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        CommandHandler("provider", provider_command)
    )
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("sources", sources_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, question_handler)
    )
    application.add_handler(
        MessageHandler(filters.COMMAND, unknown_command)
    )
    return application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    application = build_application()
    print("=============== TELEGRAM BOT ===============")
    print("Polling started. Press Ctrl+C to stop.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
