from __future__ import annotations

from decimal import Decimal
from time import perf_counter
from typing import Any, Callable

from pydantic import ValidationError

from scripts.rag.providers import TextProvider
from scripts.rag.schemas import detect_question_language

from .nbu_exchange import NbuExchangeRateTool
from .router import ToolRouter, is_exchange_rate_candidate
from .schemas import (
    ExchangeRateInput,
    ExchangeRateResult,
    ExternalToolAnswer,
    ExternalToolError,
    TOOL_NAME,
    ToolRoutingError,
)


ToolCallable = Callable[[ExchangeRateInput], ExchangeRateResult]


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def build_exchange_rate_answer(
    result: ExchangeRateResult,
    language: str,
) -> str:
    rate = _decimal_text(result.rate_uah)
    amount = _decimal_text(result.amount)
    converted = _decimal_text(result.converted_amount_uah)
    effective_date = result.effective_date.isoformat()
    special = result.special_conditions

    if language == "en":
        answer = (
            f"According to the official NBU rate effective {effective_date}, "
            f"1 {result.currency_code} = {rate} UAH."
        )
        if result.amount != Decimal("1"):
            answer += (
                f" {amount} {result.currency_code} = {converted} UAH."
            )
        if special:
            answer += " The NBU marks this rate as calculated under special conditions."
        return answer

    if language == "ru":
        answer = (
            f"По официальному курсу НБУ на {effective_date}: "
            f"1 {result.currency_code} = {rate} грн."
        )
        if result.amount != Decimal("1"):
            answer += (
                f" {amount} {result.currency_code} = {converted} грн."
            )
        if special:
            answer += " НБУ обозначает этот курс как рассчитанный в особых условиях."
        return answer

    answer = (
        f"За офіційним курсом НБУ на {effective_date}: "
        f"1 {result.currency_code} = {rate} грн."
    )
    if result.amount != Decimal("1"):
        answer += f" {amount} {result.currency_code} = {converted} грн."
    if special:
        answer += " НБУ позначає цей курс як розрахований в особливих умовах."
    return answer


def format_external_tool_answer(answer: ExternalToolAnswer) -> str:
    lines: list[str] = []
    if answer.notice:
        lines.extend([f"Примітка: {answer.notice}", ""])
    lines.extend(
        [
            answer.answer,
            "",
            f"Tool: {answer.tool_name}",
            f"Source: {answer.result.source}",
            f"Effective date: {answer.result.effective_date.isoformat()}",
            f"Router provider: {answer.router_provider}",
            f"Latency: {answer.latency_ms:.0f} ms",
        ]
    )
    return "\n".join(lines)


class ExternalToolOrchestrator:
    def __init__(
        self,
        providers: dict[str, TextProvider],
        exchange_tool: NbuExchangeRateTool | None = None,
    ) -> None:
        self.router = ToolRouter(providers)
        self.exchange_tool = exchange_tool or NbuExchangeRateTool()
        self.registry: dict[str, ToolCallable] = {
            TOOL_NAME: self.exchange_tool.execute,
        }

    @staticmethod
    def is_candidate(question: str) -> bool:
        return is_exchange_rate_candidate(question)

    def execute(
        self,
        tool_name: str,
        arguments: ExchangeRateInput | dict[str, Any],
    ) -> ExchangeRateResult:
        tool = self.registry.get(tool_name)
        if tool is None:
            raise ExternalToolError(
                f"Tool не входить до allowlist: {tool_name}"
            )
        try:
            validated = (
                arguments
                if isinstance(arguments, ExchangeRateInput)
                else ExchangeRateInput.model_validate(arguments)
            )
        except ValidationError as error:
            raise ExternalToolError(
                "Некоректні input parameters для exchange-rate tool"
            ) from error
        return tool(validated)

    def answer_direct(
        self,
        arguments: ExchangeRateInput | dict[str, Any],
        question: str = "",
    ) -> ExternalToolAnswer:
        started = perf_counter()
        try:
            validated = (
                arguments
                if isinstance(arguments, ExchangeRateInput)
                else ExchangeRateInput.model_validate(arguments)
            )
        except ValidationError as error:
            raise ExternalToolError(
                "Некоректні input parameters для exchange-rate tool"
            ) from error
        result = self.execute(TOOL_NAME, validated)
        language = detect_question_language(question or "Який курс?")
        return ExternalToolAnswer(
            question=question,
            answer=build_exchange_rate_answer(result, language),
            tool_input=validated,
            result=result,
            router_provider="direct",
            latency_ms=(perf_counter() - started) * 1000,
        )

    def try_answer(
        self,
        question: str,
        provider_name: str,
    ) -> ExternalToolAnswer | None:
        if not self.is_candidate(question):
            return None

        started = perf_counter()
        outcome = self.router.route(question, provider_name)
        decision = outcome.decision
        if decision.action == "rag":
            return None
        if decision.arguments is None or decision.tool_name is None:
            raise ToolRoutingError("Router не повернув tool arguments")

        result = self.execute(decision.tool_name, decision.arguments)
        language = detect_question_language(question)
        return ExternalToolAnswer(
            question=question,
            answer=build_exchange_rate_answer(result, language),
            tool_input=decision.arguments,
            result=result,
            router_provider=outcome.provider_name,
            latency_ms=(perf_counter() - started) * 1000,
            notice=outcome.notice,
        )
