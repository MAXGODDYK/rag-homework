from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from scripts.rag.schemas import RagAnswer
from scripts.telegram_bot.handlers import (
    provider_command,
    question_handler,
    rate_command,
    reset_command,
    sources_command,
)
from scripts.telegram_bot.rate_limit import RateLimitDecision
from scripts.tools.schemas import (
    ExchangeRateInput,
    ExchangeRateResult,
    ExternalToolAnswer,
)


class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeService:
    settings = SimpleNamespace(maximum_question_length=1000)

    def provider_status(self):
        return {
            "openai": {"available": True, "reason": "test"},
            "freemodel": {"available": True, "reason": "test"},
            "local": {"available": True, "reason": "test"},
        }

    def answer(self, question: str, provider_name: str):
        raise AssertionError("RAG must not run for a tool answer")


class FakeLimiter:
    def check_and_record(self, user_id: int, provider_name: str):
        return RateLimitDecision(True)


class FakeBot:
    async def send_chat_action(self, chat_id: int, action: str) -> None:
        return None


def tool_answer() -> ExternalToolAnswer:
    tool_input = ExchangeRateInput(
        currency_code="EUR",
        amount=Decimal("100"),
        date=date(2026, 8, 11),
    )
    result = ExchangeRateResult(
        source_url="https://bank.gov.ua/example",
        currency_code="EUR",
        currency_name="Євро",
        requested_date=date(2026, 8, 11),
        effective_date=date(2026, 8, 11),
        rate_uah=Decimal("51.8"),
        amount=Decimal("100"),
        converted_amount_uah=Decimal("5180.00"),
        special_conditions=False,
        retrieved_at_utc=datetime.now(timezone.utc),
    )
    return ExternalToolAnswer(
        question="Скільки гривень потрібно для 100 EUR?",
        answer="За офіційним курсом НБУ: 100 EUR = 5180 грн.",
        tool_input=tool_input,
        result=result,
        router_provider="freemodel",
        latency_ms=10,
    )


class FakeToolOrchestrator:
    def answer_direct(self, arguments, question: str):
        return tool_answer()

    def try_answer(self, question: str, provider_name: str):
        return tool_answer()


def context(args: list[str] | None = None):
    return SimpleNamespace(
        args=args or [],
        user_data={},
        bot=FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "rag_service": FakeService(),
                "rate_limiter": FakeLimiter(),
                "tool_orchestrator": FakeToolOrchestrator(),
            }
        ),
    )


def update(message: FakeMessage):
    return SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=7),
        effective_chat=SimpleNamespace(id=11),
    )


def test_provider_switch_and_reset() -> None:
    message = FakeMessage()
    handler_context = context(["local"])
    handler_context.user_data["last_tool_result"] = tool_answer()

    asyncio.run(
        provider_command(update(message), handler_context)
    )

    assert handler_context.user_data["provider"] == "local"
    assert "local" in message.replies[-1]

    asyncio.run(reset_command(update(message), handler_context))

    assert handler_context.user_data["provider"] == "openai"
    assert "last_result" not in handler_context.user_data
    assert "last_tool_result" not in handler_context.user_data


def test_freemodel_provider_switch() -> None:
    message = FakeMessage()
    handler_context = context(["freemodel"])

    asyncio.run(provider_command(update(message), handler_context))

    assert handler_context.user_data["provider"] == "freemodel"
    assert "freemodel" in message.replies[-1]


def test_sources_lists_last_retrieved_chunks() -> None:
    message = FakeMessage()
    handler_context = context()
    handler_context.user_data["last_result"] = RagAnswer(
        question="Question",
        answer="Answer",
        citations=("chunk_001",),
        retrieved_chunks=(
            {
                "chunk_id": "chunk_001",
                "source_file": "data/raw/source.html",
                "section": "Section",
                "reranker_raw_score": 0.75,
                "reranker_score": 0.8,
                "text": "Context",
            },
        ),
        provider="local",
        is_fallback=False,
        latency_ms=10.0,
    )

    asyncio.run(sources_command(update(message), handler_context))

    response = "\n".join(message.replies)
    assert "chunk_001" in response
    assert "data/raw/source.html" in response
    assert "0.7500" in response


def test_rate_command_and_tool_sources() -> None:
    message = FakeMessage("/rate EUR 100 2026-08-11")
    handler_context = context(["EUR", "100", "2026-08-11"])

    asyncio.run(rate_command(update(message), handler_context))

    assert "last_tool_result" in handler_context.user_data
    assert "5180" in message.replies[-1]

    sources_message = FakeMessage("/sources")
    asyncio.run(
        sources_command(update(sources_message), handler_context)
    )
    response = "\n".join(sources_message.replies)
    assert "get_nbu_exchange_rate" in response
    assert "National Bank of Ukraine" in response
    assert "2026-08-11" in response


def test_natural_language_tool_call_skips_rag() -> None:
    message = FakeMessage(
        "Скільки гривень потрібно для 100 EUR сьогодні?"
    )
    handler_context = context()
    handler_context.user_data["provider"] = "freemodel"

    asyncio.run(question_handler(update(message), handler_context))

    assert "last_tool_result" in handler_context.user_data
    assert "last_result" not in handler_context.user_data
    assert "get_nbu_exchange_rate" in message.replies[-1]


def test_invalid_rate_command_returns_without_tool_result() -> None:
    message = FakeMessage("/rate US")
    handler_context = context(["US"])

    asyncio.run(rate_command(update(message), handler_context))

    assert "last_tool_result" not in handler_context.user_data
    assert "Некоректні параметри" in message.replies[-1]
