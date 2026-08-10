from __future__ import annotations

from types import SimpleNamespace

from config.settings import Settings
from scripts.rag.providers import FreeModelProvider, OpenAIProvider


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text='{"answer":"ok"}')


class FakeChatCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"answer":"ok"}'
                    )
                )
            ]
        )


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


def test_freemodel_provider_uses_chat_completions_api() -> None:
    settings = Settings(
        telegram_bot_token="",
        openai_api_key="",
        hf_token="",
        local_adapter_path=None,
        freemodel_api_key="test-key",
        freemodel_model="auto",
    )
    completions = FakeChatCompletions()
    provider = FreeModelProvider(settings)
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )

    output = provider.generate("grounded prompt")

    assert output == '{"answer":"ok"}'
    assert completions.calls == [
        {
            "model": "auto",
            "messages": [
                {"role": "user", "content": "grounded prompt"}
            ],
            "max_tokens": 384,
        }
    ]
