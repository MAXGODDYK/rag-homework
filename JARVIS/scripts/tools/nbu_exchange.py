from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import httpx
from pydantic import ValidationError

from .schemas import (
    ExchangeRateInput,
    ExchangeRateResult,
    ExternalToolError,
    NBU_SOURCE_NAME,
    NbuRateRow,
    TOOL_NAME,
    kyiv_today,
    utc_now,
)


NBU_EXCHANGE_ENDPOINT = (
    "https://bank.gov.ua/NBUStatService/v1/"
    "statdirectory/exchange"
)
DEFAULT_TIMEOUT_SECONDS = 10.0


class NbuExchangeRateTool:
    name = TOOL_NAME
    tool_type = "read"

    def __init__(
        self,
        client: httpx.Client | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._client = client
        self.timeout_seconds = timeout_seconds

    def _request(self, params: dict[str, str]) -> httpx.Response:
        try:
            if self._client is not None:
                return self._client.get(
                    NBU_EXCHANGE_ENDPOINT,
                    params=params,
                    timeout=self.timeout_seconds,
                )
            with httpx.Client(timeout=self.timeout_seconds) as client:
                return client.get(
                    NBU_EXCHANGE_ENDPOINT,
                    params=params,
                )
        except httpx.TimeoutException as error:
            raise ExternalToolError(
                "НБУ API не відповів у межах timeout"
            ) from error
        except httpx.HTTPError as error:
            raise ExternalToolError(
                "Не вдалося з'єднатися з НБУ API"
            ) from error

    def execute(
        self,
        tool_input: ExchangeRateInput,
    ) -> ExchangeRateResult:
        params = {
            "valcode": tool_input.currency_code,
            "json": "",
        }
        if tool_input.date is not None:
            params["date"] = tool_input.date.strftime("%Y%m%d")

        response = self._request(params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise ExternalToolError(
                f"НБУ API повернув HTTP {response.status_code}"
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise ExternalToolError(
                "НБУ API повернув некоректний JSON"
            ) from error

        if not isinstance(payload, list):
            raise ExternalToolError(
                "НБУ API повернув неочікувану структуру"
            )
        if not payload:
            raise ExternalToolError(
                f"Валюту {tool_input.currency_code} не знайдено в НБУ"
            )
        if len(payload) != 1:
            raise ExternalToolError(
                "НБУ API повернув неоднозначний результат"
            )

        try:
            row = NbuRateRow.model_validate(payload[0])
            effective_date = row.parsed_exchange_date()
        except (ValidationError, ValueError) as error:
            raise ExternalToolError(
                "НБУ API повернув неповні або некоректні дані"
            ) from error

        if row.cc != tool_input.currency_code:
            raise ExternalToolError(
                "Currency code у відповіді НБУ не збігається із запитом"
            )

        converted = (row.rate * tool_input.amount).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        requested_date = tool_input.date or kyiv_today()

        return ExchangeRateResult(
            tool_name=TOOL_NAME,
            source=NBU_SOURCE_NAME,
            source_url=str(response.request.url),
            currency_code=row.cc,
            currency_name=row.txt,
            requested_date=requested_date,
            effective_date=effective_date,
            rate_uah=row.rate,
            amount=tool_input.amount,
            converted_amount_uah=converted,
            special_conditions=row.special == "Y",
            retrieved_at_utc=utc_now(),
        )
