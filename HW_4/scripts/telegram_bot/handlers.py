from __future__ import annotations

import asyncio

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from scripts.rag.schemas import RagAnswer, format_rag_answer


DEFAULT_PROVIDER = "openai"


def _objects(context: ContextTypes.DEFAULT_TYPE):
    service = context.application.bot_data["rag_service"]
    limiter = context.application.bot_data["rate_limiter"]
    return service, limiter


async def _send_long_message(
    update: Update,
    text: str,
) -> None:
    message = update.effective_message
    if message is None:
        return

    maximum_length = 3900
    remaining = text
    while remaining:
        if len(remaining) <= maximum_length:
            part = remaining
            remaining = ""
        else:
            split_at = remaining.rfind("\n", 0, maximum_length)
            if split_at < maximum_length // 2:
                split_at = maximum_length
            part = remaining[:split_at]
            remaining = remaining[split_at:].lstrip()
        await message.reply_text(part)


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    text = (
        "Вітаю! Це grounded RAG-бот для планування навчання.\n\n"
        "Надішліть запитання звичайним повідомленням. "
        "Відповідь буде побудована тільки за локальною knowledge base "
        "і міститиме chunk citations.\n\n"
        "Команди: /help, /provider, /status, /sources, /reset"
    )
    await update.effective_message.reply_text(text)


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    text = (
        "Приклад:\n"
        "Як скласти реалістичний план підготовки до іспиту?\n\n"
        "/provider openai — OpenAI gpt-4.1-mini\n"
        "/provider freemodel — FreeModel OpenAI-compatible API\n"
        "/provider local — fine-tuned Qwen3-4B\n"
        "/status — стан моделей і лімітів\n"
        "/sources — chunks останньої відповіді\n"
        "/reset — скинути provider та останній результат"
    )
    await update.effective_message.reply_text(text)


async def provider_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    service, _ = _objects(context)
    if not context.args:
        current = context.user_data.get(
            "provider",
            DEFAULT_PROVIDER,
        )
        await update.effective_message.reply_text(
            f"Поточний provider: {current}\n"
            "Використання: /provider openai, freemodel або local"
        )
        return

    provider_name = context.args[0].lower()
    if provider_name not in {"openai", "freemodel", "local"}:
        await update.effective_message.reply_text(
            "Provider повинен бути openai, freemodel або local."
        )
        return

    if provider_name in {"freemodel", "local"}:
        status = service.provider_status()[provider_name]
        if not status["available"]:
            await update.effective_message.reply_text(
                f"{provider_name} provider недоступний: "
                f"{status['reason']}"
            )
            return

    context.user_data["provider"] = provider_name
    await update.effective_message.reply_text(
        f"Provider змінено на: {provider_name}"
    )


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    service, limiter = _objects(context)
    provider_name = context.user_data.get(
        "provider",
        DEFAULT_PROVIDER,
    )
    statuses = service.provider_status()
    openai_used, openai_maximum = limiter.openai_daily_usage()
    freemodel_used, freemodel_maximum = (
        limiter.freemodel_daily_usage()
    )

    lines = [
        f"Поточний provider: {provider_name}",
        (
            "OpenAI: "
            + (
                "available"
                if statuses["openai"]["available"]
                else f"unavailable — {statuses['openai']['reason']}"
            )
        ),
        (
            "FreeModel: "
            + (
                "available"
                if statuses["freemodel"]["available"]
                else (
                    "unavailable — "
                    f"{statuses['freemodel']['reason']}"
                )
            )
        ),
        (
            "Local: "
            + (
                "available"
                if statuses["local"]["available"]
                else f"unavailable — {statuses['local']['reason']}"
            )
        ),
        f"OpenAI requests today: {openai_used}/{openai_maximum}",
        (
            "FreeModel requests today: "
            f"{freemodel_used}/{freemodel_maximum}"
        ),
    ]
    await update.effective_message.reply_text("\n".join(lines))


async def sources_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    result: RagAnswer | None = context.user_data.get("last_result")
    if result is None:
        await update.effective_message.reply_text(
            "Ще немає останньої відповіді."
        )
        return

    lines = ["Retrieved chunks:"]
    for rank, chunk in enumerate(result.retrieved_chunks, start=1):
        lines.extend(
            [
                "",
                f"Top-{rank}: {chunk['chunk_id']}",
                f"Source: {chunk['source_file']}",
                f"Section: {chunk['section']}",
                (
                    "Score: "
                    f"{chunk['reranker_raw_score']:.4f} raw"
                ),
            ]
        )
    await _send_long_message(update, "\n".join(lines))


async def reset_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    context.user_data.pop("last_result", None)
    context.user_data["provider"] = DEFAULT_PROVIDER
    await update.effective_message.reply_text(
        "Provider скинуто до openai; останній результат очищено."
    )


async def question_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None or not message.text:
        return

    service, limiter = _objects(context)
    question = message.text.strip()
    provider_name = context.user_data.get(
        "provider",
        DEFAULT_PROVIDER,
    )

    if len(question) > service.settings.maximum_question_length:
        await message.reply_text(
            "Запитання занадто довге. Максимум: "
            f"{service.settings.maximum_question_length} символів."
        )
        return

    decision = limiter.check_and_record(user.id, provider_name)
    if not decision.allowed:
        if (
            provider_name in {"openai", "freemodel"}
            and "денний ліміт" in decision.reason
            and service.provider_status()["local"]["available"]
        ):
            exhausted_provider = provider_name
            provider_name = "local"
            second_decision = limiter.check_and_record(
                user.id,
                provider_name,
            )
            if not second_decision.allowed:
                await message.reply_text(second_decision.reason)
                return
            await message.reply_text(
                f"Денний ліміт {exhausted_provider} вичерпано; "
                "використовую local Qwen."
            )
        else:
            await message.reply_text(decision.reason)
            return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

    try:
        result = await asyncio.to_thread(
            service.answer,
            question,
            provider_name,
        )
    except Exception as error:
        await message.reply_text(
            "Не вдалося створити відповідь: "
            f"{type(error).__name__}: {error}"
        )
        return

    context.user_data["last_result"] = result
    await _send_long_message(update, format_rag_answer(result))


async def unknown_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await update.effective_message.reply_text(
        "Невідома команда. Використайте /help."
    )
