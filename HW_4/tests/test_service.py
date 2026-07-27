from __future__ import annotations

import json

from config.settings import Settings
from scripts.rag.providers import ProviderGenerationError
from scripts.rag.service import RagAnswerService


def settings() -> Settings:
    return Settings(
        telegram_bot_token="",
        openai_api_key="test",
        hf_token="",
        local_adapter_path=None,
    )


class FakeRetriever:
    def __init__(self, score: float = 0.5) -> None:
        self.score = score

    def retrieve(self, **kwargs):
        return [
            {
                "chunk_id": "chunk_001",
                "source_file": "data/raw/source.html",
                "text": "Regular breaks support effective study.",
                "metadata": {"section": "Breaks"},
                "reranker_raw_score": self.score,
                "reranker_score": 0.6,
            }
        ]


class FakeProvider:
    def __init__(self, outputs: list[str], name: str) -> None:
        self.outputs = outputs
        self.name = name
        self.calls = 0

    def availability(self):
        return True, "test"

    def generate(self, prompt: str) -> str:
        output = self.outputs[self.calls]
        self.calls += 1
        return output


class FailingProvider:
    name = "openai"

    def availability(self):
        return True, "test"

    def generate(self, prompt: str) -> str:
        raise ProviderGenerationError("network")


def valid_output() -> str:
    return json.dumps(
        {
            "answer": "Take regular breaks.",
            "citations": ["chunk_001"],
            "insufficient_context": False,
        }
    )


def test_confidence_gate_skips_provider() -> None:
    provider = FakeProvider([valid_output()], "openai")
    service = RagAnswerService(
        settings=settings(),
        retriever=FakeRetriever(score=0.0001),
        providers={"openai": provider, "local": provider},
    )

    result = service.answer("How to make borscht?")

    assert result.is_fallback is True
    assert provider.calls == 0


def test_invalid_output_gets_one_repair_attempt() -> None:
    provider = FakeProvider(["not json", valid_output()], "openai")
    service = RagAnswerService(
        settings=settings(),
        retriever=FakeRetriever(),
        providers={"openai": provider, "local": provider},
    )

    result = service.answer("Should I take breaks?")

    assert provider.calls == 2
    assert result.citations == ("chunk_001",)


def test_second_contract_failure_returns_safe_fallback() -> None:
    provider = FakeProvider(["bad", "still bad"], "openai")
    service = RagAnswerService(
        settings=settings(),
        retriever=FakeRetriever(),
        providers={"openai": provider, "local": provider},
    )

    result = service.answer("Should I take breaks?")

    assert result.is_fallback is True
    assert result.citations == ()


def test_openai_error_uses_local_provider() -> None:
    local = FakeProvider([valid_output()], "local")
    service = RagAnswerService(
        settings=settings(),
        retriever=FakeRetriever(),
        providers={
            "openai": FailingProvider(),
            "local": local,
        },
    )

    result = service.answer("Should I take breaks?")

    assert result.provider == "local"
    assert result.notice is not None
    assert local.calls == 1
