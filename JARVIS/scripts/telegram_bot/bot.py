from __future__ import annotations

import logging
import os
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

from jarvis.runtime import Runtime, build_runtime

from config.settings import load_settings
from scripts.tools.orchestrator import ExternalToolOrchestrator
from scripts.telegram_bot.handlers import (
    help_command,
    provider_command,
    question_handler,
    rate_command,
    reset_command,
    sources_command,
    start_command,
    status_command,
    unknown_command,
)
from scripts.telegram_bot.rate_limit import BotRateLimiter
from scripts.telegram_bot.jarvis_handlers import (
    approvals_command,
    clearfiles_command,
    delete_command,
    document_handler,
    files_command,
    jarvis_question_handler,
    jarvis_reset_command,
    jarvis_sources_command,
    mode_command,
    scope_command,
    uploadinfo_command,
    use_command,
    whoami_command,
)


def build_application(runtime: Runtime | None = None):
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
    if os.getenv("JARVIS_LEXICAL_ONLY") == "1":
        from scripts.rag.providers import build_text_providers

        class CompactService:
            def __init__(self):
                self.settings = settings
                self.providers = build_text_providers(settings)

            def provider_status(self):
                return {
                    name: {"available": provider.availability()[0], "reason": provider.availability()[1]}
                    for name, provider in self.providers.items()
                }

            def answer(self, *_args, **_kwargs):
                raise RuntimeError("Legacy HW4 RAG is disabled in the compact sidecar; use an allowlisted JARVIS user")

        rag_service = CompactService()
    else:
        from scripts.rag.service import RagAnswerService

        rag_service = RagAnswerService(settings=settings)
    application.bot_data["rag_service"] = rag_service
    application.bot_data["tool_orchestrator"] = (
        ExternalToolOrchestrator(providers=rag_service.providers)
    )
    application.bot_data["rate_limiter"] = BotRateLimiter(
        state_path=PROJECT_ROOT / "local_state" / "bot_usage.json",
        per_user_limit=settings.per_user_request_limit,
        window_seconds=settings.per_user_window_seconds,
        openai_daily_limit=settings.openai_daily_request_limit,
        freemodel_daily_limit=settings.freemodel_daily_request_limit,
    )
    application.bot_data["jarvis_runtime"] = runtime or build_runtime()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        CommandHandler("provider", provider_command)
    )
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("rate", rate_command))
    application.add_handler(CommandHandler("files", files_command))
    application.add_handler(CommandHandler("uploadinfo", uploadinfo_command))
    application.add_handler(CommandHandler("use", use_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("clearfiles", clearfiles_command))
    application.add_handler(CommandHandler("mode", mode_command))
    application.add_handler(CommandHandler("scope", scope_command))
    application.add_handler(CommandHandler("approvals", approvals_command))
    application.add_handler(CommandHandler("whoami", whoami_command))

    async def combined_sources(update, context):
        if not await jarvis_sources_command(update, context):
            await sources_command(update, context)

    application.add_handler(CommandHandler("sources", combined_sources))
    application.add_handler(CommandHandler("reset", jarvis_reset_command))
    application.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, jarvis_question_handler)
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
