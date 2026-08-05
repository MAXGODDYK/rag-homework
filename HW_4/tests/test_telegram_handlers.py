from __future__ import annotations

import asyncio
from types import SimpleNamespace

from scripts.rag.schemas import RagAnswer
from scripts.telegram_bot.handlers import (
    provider_command,
    reset_command,
    sources_command,
)


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeService:
    def provider_status(self):
        return {
            "openai": {"available": True, "reason": "test"},
            "freemodel": {"available": True, "reason": "test"},
            "local": {"available": True, "reason": "test"},
        }


def context(args: list[str] | None = None):
    return SimpleNamespace(
        args=args or [],
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "rag_service": FakeService(),
                "rate_limiter": object(),
            }
        ),
    )


def update(message: FakeMessage):
    return SimpleNamespace(effective_message=message)


def test_provider_switch_and_reset() -> None:
    message = FakeMessage()
    handler_context = context(["local"])

    asyncio.run(
        provider_command(update(message), handler_context)
    )

    assert handler_context.user_data["provider"] == "local"
    assert "local" in message.replies[-1]

    asyncio.run(reset_command(update(message), handler_context))

    assert handler_context.user_data["provider"] == "openai"
    assert "last_result" not in handler_context.user_data


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
