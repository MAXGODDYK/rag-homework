from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from scripts.rag.providers import ProviderError, TextProvider

from .schemas import ToolRouteDecision, ToolRoutingError, kyiv_today


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTER_PROMPT_PATH = PROJECT_ROOT / "prompts" / "tool_router_prompt.txt"
REPAIR_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "tool_router_repair_prompt.txt"
)

CURRENCY_HINT_PATTERN = re.compile(
    r"(?:\b(?:USD|EUR|PLN|GBP|CHF|CZK|CAD|JPY|CNY|UAH)\b|"
    r"курс(?:у|ом|а|и)?|валют|обмінн|обменн|exchange\s+rate|"
    r"currency|грив|долар|доллар|євро|евро|злот|фунт)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class RouteOutcome:
    decision: ToolRouteDecision
    provider_name: str
    notice: str | None = None


def is_exchange_rate_candidate(question: str) -> bool:
    return bool(CURRENCY_HINT_PATTERN.search(question))


def _extract_json_object(raw_output: str) -> dict:
    text = raw_output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        value = json.loads(text)
    except json.JSONDecodeError as first_error:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Router output does not contain JSON") from first_error
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError as error:
            raise ValueError("Router output contains invalid JSON") from error

    if not isinstance(value, dict):
        raise ValueError("Router output must be a JSON object")
    return value


class ToolRouter:
    def __init__(self, providers: dict[str, TextProvider]) -> None:
        self.providers = providers
        self._router_template = ROUTER_PROMPT_PATH.read_text(
            encoding="utf-8"
        )
        self._repair_template = REPAIR_PROMPT_PATH.read_text(
            encoding="utf-8"
        )

    def _provider(self, provider_name: str) -> TextProvider:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise ToolRoutingError(
                f"Невідомий router provider: {provider_name}"
            )
        return provider

    def _generate_with_fallback(
        self,
        prompt: str,
        provider_name: str,
    ) -> tuple[str, str, str | None]:
        provider = self._provider(provider_name)
        available, reason = provider.availability()
        if available:
            try:
                return provider.generate(prompt), provider_name, None
            except ProviderError as first_error:
                if provider_name not in {"openai", "freemodel"}:
                    raise ToolRoutingError(
                        f"Router provider failed: {type(first_error).__name__}"
                    ) from first_error
        else:
            first_error = ToolRoutingError(reason)

        local = self.providers.get("local")
        if provider_name in {"openai", "freemodel"} and local is not None:
            local_available, local_reason = local.availability()
            if local_available:
                try:
                    output = local.generate(prompt)
                except ProviderError as local_error:
                    raise ToolRoutingError(
                        "Зовнішній і local router providers недоступні"
                    ) from local_error
                return (
                    output,
                    "local",
                    f"{provider_name} router недоступний; використано local.",
                )
            raise ToolRoutingError(
                f"Router provider недоступний; local fallback: {local_reason}"
            ) from first_error

        raise ToolRoutingError(str(first_error)) from first_error

    @staticmethod
    def _parse(raw_output: str) -> ToolRouteDecision:
        payload = _extract_json_object(raw_output)
        return ToolRouteDecision.model_validate(payload)

    def route(
        self,
        question: str,
        provider_name: str,
    ) -> RouteOutcome:
        if not is_exchange_rate_candidate(question):
            return RouteOutcome(
                decision=ToolRouteDecision(
                    action="rag",
                    tool_name=None,
                    arguments=None,
                ),
                provider_name="prefilter",
            )

        current_date = kyiv_today().isoformat()
        prompt = self._router_template.format(
            current_date=current_date,
            question=question,
        )
        raw_output, actual_provider, notice = self._generate_with_fallback(
            prompt,
            provider_name,
        )

        try:
            decision = self._parse(raw_output)
        except (ValueError, ValidationError):
            repair_prompt = self._repair_template.format(
                current_date=current_date,
                question=question,
                invalid_output=raw_output,
            )
            provider = self._provider(actual_provider)
            try:
                repaired = provider.generate(repair_prompt)
                decision = self._parse(repaired)
            except (ProviderError, ValueError, ValidationError) as error:
                raise ToolRoutingError(
                    "Router двічі порушив JSON/tool contract. "
                    "Використайте /rate USD [amount] [YYYY-MM-DD]."
                ) from error

        return RouteOutcome(
            decision=decision,
            provider_name=actual_provider,
            notice=notice,
        )
