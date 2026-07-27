from __future__ import annotations

from types import SimpleNamespace

from config.settings import Settings
from scripts.rag.providers import OpenAIProvider


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text='{"answer":"ok"}')


def test_openai_provider_uses_responses_api_output_text() -> None:
    settings = Settings(
        telegram_bot_token="",
        openai_api_key="test-key",
        hf_token="",
        local_adapter_path=None,
    )
    responses = FakeResponses()
    provider = OpenAIProvider(settings)
    provider._client = SimpleNamespace(responses=responses)

    output = provider.generate("grounded prompt")

    assert output == '{"answer":"ok"}'
    assert responses.calls == [
        {
            "model": "gpt-4.1-mini",
            "input": "grounded prompt",
            "max_output_tokens": 384,
        }
    ]
