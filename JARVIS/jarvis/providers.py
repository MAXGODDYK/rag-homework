from __future__ import annotations

from typing import Protocol

from config.settings import Settings


class ProviderError(RuntimeError):
    """A safe remote-generation failure."""


class TextProvider(Protocol):
    name: str

    def availability(self) -> tuple[bool, str]: ...

    def generate(self, prompt: str) -> str: ...


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def availability(self) -> tuple[bool, str]:
        return (True, f"model={self.settings.openai_model}") if self.settings.openai_api_key else (False, "OPENAI_API_KEY is not configured")

    def generate(self, prompt: str) -> str:
        if not self.availability()[0]:
            raise ProviderError("OpenAI is not configured")
        try:
            if self._client is None:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.settings.openai_api_key)
            response = self._client.responses.create(
                model=self.settings.openai_model,
                input=prompt,
                max_output_tokens=self.settings.maximum_answer_tokens,
            )
            text = str(getattr(response, "output_text", "")).strip()
        except Exception as error:
            raise ProviderError(f"OpenAI generation failed: {type(error).__name__}") from error
        if not text:
            raise ProviderError("OpenAI returned an empty answer")
        return text


class FreeModelProvider:
    name = "freemodel"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def availability(self) -> tuple[bool, str]:
        return (True, f"model={self.settings.freemodel_model}") if self.settings.freemodel_api_key else (False, "FREEMODEL_API_KEY is not configured")

    def generate(self, prompt: str) -> str:
        if not self.availability()[0]:
            raise ProviderError("FreeModel is not configured")
        try:
            if self._client is None:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.settings.freemodel_api_key, base_url=self.settings.freemodel_base_url)
            response = self._client.chat.completions.create(
                model=self.settings.freemodel_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.settings.maximum_answer_tokens,
            )
            text = str(response.choices[0].message.content or "").strip()
        except Exception as error:
            raise ProviderError(f"FreeModel generation failed: {type(error).__name__}") from error
        if not text:
            raise ProviderError("FreeModel returned an empty answer")
        return text


def build_text_providers(settings: Settings) -> dict[str, TextProvider]:
    return {"freemodel": FreeModelProvider(settings), "openai": OpenAIProvider(settings)}
