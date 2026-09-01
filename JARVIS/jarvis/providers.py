from __future__ import annotations

import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config.settings import Settings


class ProviderError(RuntimeError):
    """A safe local-generation failure that never exposes transport details."""


class TextProvider(Protocol):
    name: str

    def availability(self) -> tuple[bool, str]: ...

    def generate(self, prompt: str) -> str: ...


class OllamaProvider:
    """Local Qwen generation through the Ollama loopback API."""

    name = "local"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
    @property
    def _base_url(self) -> str:
        return self.settings.ollama_base_url.rstrip("/")

    def availability(self) -> tuple[bool, str]:
        try:
            with urlopen(f"{self._base_url}/api/tags", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, HTTPError, TimeoutError, OSError, json.JSONDecodeError):
            return False, "Ollama is not running on this PC"

        models = payload.get("models", []) if isinstance(payload, dict) else []
        names = {str(item.get("name", "")) for item in models if isinstance(item, dict)}
        if self.settings.ollama_model not in names:
            return False, f"model {self.settings.ollama_model} is not downloaded"
        return True, f"local model={self.settings.ollama_model}"

    def generate(self, prompt: str) -> str:
        if not self.availability()[0]:
            raise ProviderError("The local Ollama model is unavailable")
        body = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.1, "num_ctx": 8192},
        }
        request = Request(
            f"{self._base_url}/api/generate",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, HTTPError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise ProviderError("Local Ollama generation failed") from error
        text = str(payload.get("response", "")).strip() if isinstance(payload, dict) else ""
        if not text:
            raise ProviderError("The local model returned an empty answer")
        return text


def build_text_providers(settings: Settings) -> dict[str, TextProvider]:
    return {"local": OllamaProvider(settings)}
