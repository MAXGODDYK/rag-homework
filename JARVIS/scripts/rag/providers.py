from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Protocol

from config.settings import Settings


class ProviderError(RuntimeError):
    """Base provider failure."""


class ProviderUnavailableError(ProviderError):
    """The configured provider cannot be used."""


class ProviderGenerationError(ProviderError):
    """The provider failed while generating a response."""


class TextProvider(Protocol):
    name: str

    def generate(self, prompt: str) -> str:
        ...

    def availability(self) -> tuple[bool, str]:
        ...


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def availability(self) -> tuple[bool, str]:
        if not self.settings.openai_api_key:
            return False, "OPENAI_API_KEY не налаштовано"
        return True, f"model={self.settings.openai_model}"

    def _get_client(self):
        available, reason = self.availability()
        if not available:
            raise ProviderUnavailableError(reason)
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.settings.openai_api_key,
            )
        return self._client

    def generate(self, prompt: str) -> str:
        try:
            response = self._get_client().responses.create(
                model=self.settings.openai_model,
                input=prompt,
                max_output_tokens=self.settings.maximum_answer_tokens,
            )
        except ProviderUnavailableError:
            raise
        except Exception as error:
            raise ProviderGenerationError(
                f"OpenAI generation failed: {type(error).__name__}"
            ) from error

        output_text = getattr(response, "output_text", "")
        if not output_text or not output_text.strip():
            raise ProviderGenerationError(
                "OpenAI повернув порожній output_text"
            )
        return output_text.strip()


class FreeModelProvider:
    name = "freemodel"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def availability(self) -> tuple[bool, str]:
        if not self.settings.freemodel_api_key:
            return False, "FREEMODEL_API_KEY не налаштовано"
        return True, (
            f"model={self.settings.freemodel_model}; "
            f"base_url={self.settings.freemodel_base_url}"
        )

    def _get_client(self):
        available, reason = self.availability()
        if not available:
            raise ProviderUnavailableError(reason)
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.settings.freemodel_api_key,
                base_url=self.settings.freemodel_base_url,
            )
        return self._client

    def generate(self, prompt: str) -> str:
        try:
            response = self._get_client().chat.completions.create(
                model=self.settings.freemodel_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.settings.maximum_answer_tokens,
            )
        except ProviderUnavailableError:
            raise
        except Exception as error:
            raise ProviderGenerationError(
                "FreeModel generation failed: "
                f"{type(error).__name__}"
            ) from error

        choices = getattr(response, "choices", ())
        output_text = (
            getattr(choices[0].message, "content", "")
            if choices
            else ""
        )
        if not output_text or not output_text.strip():
            raise ProviderGenerationError(
                "FreeModel повернув порожній message content"
            )
        return output_text.strip()


class LocalQwenProvider:
    name = "local"

    def __init__(
        self,
        settings: Settings,
        *,
        use_adapter: bool = True,
        provider_name: str = "local",
    ) -> None:
        self.settings = settings
        self.use_adapter = use_adapter
        self.name = provider_name
        self._tokenizer = None
        self._model = None
        self._load_lock = Lock()
        self._generation_lock = Lock()

    def availability(self) -> tuple[bool, str]:
        adapter_path = self.settings.local_adapter_path
        if self.use_adapter:
            if adapter_path is None:
                return False, "LOCAL_ADAPTER_PATH не налаштовано"
            if not adapter_path.exists():
                return False, f"LoRA adapter не знайдено: {adapter_path}"

        try:
            import torch
        except ImportError:
            return False, "PyTorch не встановлено"

        if not torch.cuda.is_available():
            return False, "CUDA-enabled PyTorch недоступний"

        suffix = f"; adapter={adapter_path}" if self.use_adapter else "; base planning model"
        return True, f"model={self.settings.local_model_name}{suffix}"

    def _load(self) -> None:
        if self._model is not None:
            return

        with self._load_lock:
            if self._model is not None:
                return

            available, reason = self.availability()
            if not available:
                raise ProviderUnavailableError(reason)

            import torch
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                BitsAndBytesConfig,
            )

            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
            token = self.settings.hf_token or None
            tokenizer = AutoTokenizer.from_pretrained(
                self.settings.local_model_name,
                token=token,
            )
            base_model = AutoModelForCausalLM.from_pretrained(
                self.settings.local_model_name,
                token=token,
                device_map="auto",
                quantization_config=quantization_config,
                dtype=torch.bfloat16,
            )
            if self.use_adapter:
                from peft import PeftModel

                model = PeftModel.from_pretrained(
                    base_model,
                    str(self.settings.local_adapter_path),
                )
            else:
                model = base_model
            model.eval()
            self._tokenizer = tokenizer
            self._model = model

    def generate(self, prompt: str) -> str:
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None

        import torch

        messages = [{"role": "user", "content": prompt}]
        rendered = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self._tokenizer(
            rendered,
            return_tensors="pt",
        ).to(self._model.device)

        try:
            with self._generation_lock, torch.inference_mode():
                generated_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=self.settings.maximum_answer_tokens,
                    do_sample=False,
                    pad_token_id=self._tokenizer.eos_token_id,
                )
        except Exception as error:
            raise ProviderGenerationError(
                f"Local generation failed: {type(error).__name__}"
            ) from error

        new_tokens = generated_ids[0, inputs["input_ids"].shape[1] :]
        output = self._tokenizer.decode(
            new_tokens,
            skip_special_tokens=True,
        ).strip()
        if not output:
            raise ProviderGenerationError(
                "Local Qwen повернула порожній output"
            )
        return output


def build_text_providers(
    settings: Settings,
) -> dict[str, TextProvider]:
    return {
        "openai": OpenAIProvider(settings),
        "freemodel": FreeModelProvider(settings),
        "local": LocalQwenProvider(settings),
    }
