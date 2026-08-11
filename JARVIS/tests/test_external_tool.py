from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from scripts.tools.nbu_exchange import NbuExchangeRateTool
from scripts.tools.orchestrator import ExternalToolOrchestrator
from scripts.tools.schemas import (
    ExchangeRateInput,
    ExternalToolError,
    kyiv_today,
)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _success_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        json=[
            {
                "r030": 840,
                "txt": "Долар США",
                "rate": 44.8305,
                "cc": "USD",
                "exchangedate": "11.08.2026",
                "special": "N",
            }
        ],
    )


def test_input_contract_normalizes_and_rejects_invalid_values() -> None:
    value = ExchangeRateInput.model_validate(
        {"currency_code": " usd ", "amount": "100.25"}
    )
    assert value.currency_code == "USD"
    assert value.amount == Decimal("100.25")

    invalid_payloads = [
        {"currency_code": "US"},
        {"currency_code": "123"},
        {"currency_code": "USD", "amount": 0},
        {"currency_code": "USD", "amount": 1000001},
        {"currency_code": "USD", "unknown": True},
        {
            "currency_code": "USD",
            "date": (kyiv_today() + timedelta(days=1)).isoformat(),
        },
    ]
    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            ExchangeRateInput.model_validate(payload)


def test_successful_nbu_response_is_normalized() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["valcode"] == "USD"
        assert request.url.params["date"] == "20260811"
        return _success_response(request)

    with _client(handler) as client:
        result = NbuExchangeRateTool(client=client).execute(
            ExchangeRateInput(
                currency_code="USD",
                amount=Decimal("100"),
                date="2026-08-11",
            )
        )

    assert calls == 1
    assert result.currency_name == "Долар США"
    assert result.requested_date.isoformat() == "2026-08-11"
    assert result.effective_date.isoformat() == "2026-08-11"
    assert result.rate_uah == Decimal("44.8305")
    assert result.converted_amount_uah == Decimal("4483.05")
    assert result.special_conditions is False


def test_nbu_null_special_is_normalized_to_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _success_response(request).json()
        payload[0]["special"] = None
        return httpx.Response(200, request=request, json=payload)

    with _client(handler) as client:
        result = NbuExchangeRateTool(client=client).execute(
            ExchangeRateInput(currency_code="USD")
        )

    assert result.special_conditions is False


@pytest.mark.parametrize(
    ("response_factory", "message"),
    [
        (
            lambda request: httpx.Response(200, request=request, json=[]),
            "не знайдено",
        ),
        (
            lambda request: httpx.Response(404, request=request),
            "HTTP 404",
        ),
        (
            lambda request: httpx.Response(500, request=request),
            "HTTP 500",
        ),
        (
            lambda request: httpx.Response(
                200, request=request, content=b"not-json"
            ),
            "некоректний JSON",
        ),
        (
            lambda request: httpx.Response(
                200, request=request, json={"cc": "USD"}
            ),
            "неочікувану структуру",
        ),
        (
            lambda request: httpx.Response(
                200,
                request=request,
                json=[{"txt": "x", "rate": -1, "cc": "USD"}],
            ),
            "неповні або некоректні",
        ),
    ],
)
def test_nbu_errors_are_safe(response_factory, message: str) -> None:
    with _client(response_factory) as client:
        tool = NbuExchangeRateTool(client=client)
        with pytest.raises(ExternalToolError, match=message):
            tool.execute(ExchangeRateInput(currency_code="USD"))


def test_timeout_is_converted_to_safe_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret details", request=request)

    with _client(handler) as client:
        with pytest.raises(ExternalToolError, match="timeout"):
            NbuExchangeRateTool(client=client).execute(
                ExchangeRateInput(currency_code="USD")
            )


def test_mismatched_currency_code_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _success_response(request).json()
        payload[0]["cc"] = "EUR"
        return httpx.Response(200, request=request, json=payload)

    with _client(handler) as client:
        with pytest.raises(ExternalToolError, match="не збігається"):
            NbuExchangeRateTool(client=client).execute(
                ExchangeRateInput(currency_code="USD")
            )


def test_invalid_input_stops_before_http_and_unknown_tool_is_blocked() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _success_response(request)

    with _client(handler) as client:
        orchestrator = ExternalToolOrchestrator(
            providers={},
            exchange_tool=NbuExchangeRateTool(client=client),
        )
        with pytest.raises(ExternalToolError):
            orchestrator.answer_direct({"currency_code": "US"})
        with pytest.raises(ExternalToolError, match="allowlist"):
            orchestrator.execute(
                "download_url",
                {"currency_code": "USD"},
            )

    assert calls == 0
