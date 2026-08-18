from __future__ import annotations

import re
from datetime import date as Date
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


TOOL_NAME = "get_nbu_exchange_rate"
NBU_SOURCE_NAME = "National Bank of Ukraine"
KYIV_TIMEZONE = ZoneInfo("Europe/Kyiv")


class ExternalToolError(RuntimeError):
    """Safe external-tool failure that may be shown to a user."""


class ToolRoutingError(RuntimeError):
    """The model did not produce a valid allowlisted tool decision."""


def kyiv_today() -> Date:
    return datetime.now(KYIV_TIMEZONE).date()


class ExchangeRateInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    currency_code: str
    date: Date | None = None
    amount: Decimal = Field(
        default=Decimal("1"),
        ge=Decimal("0.01"),
        le=Decimal("1000000"),
        max_digits=16,
        decimal_places=4,
    )

    @field_validator("currency_code", mode="before")
    @classmethod
    def normalize_currency_code(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("currency_code повинен бути рядком")
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError(
                "currency_code повинен містити рівно 3 латинські літери"
            )
        return normalized

    @field_validator("date")
    @classmethod
    def reject_future_date(cls, value: Date | None) -> Date | None:
        if value is not None and value > kyiv_today():
            raise ValueError("date не може бути в майбутньому")
        return value

    @field_serializer("amount", when_used="json")
    def serialize_amount(self, value: Decimal) -> float:
        return float(value)


class ExchangeRateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: Literal["get_nbu_exchange_rate"] = TOOL_NAME
    source: Literal["National Bank of Ukraine"] = NBU_SOURCE_NAME
    source_url: str
    currency_code: str
    currency_name: str
    requested_date: Date
    effective_date: Date
    rate_uah: Decimal
    amount: Decimal
    converted_amount_uah: Decimal
    special_conditions: bool
    retrieved_at_utc: datetime

    @field_serializer(
        "rate_uah",
        "amount",
        "converted_amount_uah",
        when_used="json",
    )
    def serialize_decimal(self, value: Decimal) -> float:
        return float(value)


class ToolRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["tool", "rag"]
    tool_name: Literal["get_nbu_exchange_rate"] | None = None
    arguments: ExchangeRateInput | None = None

    @model_validator(mode="after")
    def validate_action_fields(self) -> "ToolRouteDecision":
        if self.action == "tool":
            if self.tool_name != TOOL_NAME or self.arguments is None:
                raise ValueError(
                    "tool action вимагає allowlisted tool_name та arguments"
                )
        elif self.tool_name is not None or self.arguments is not None:
            raise ValueError(
                "rag action не повинен містити tool_name або arguments"
            )
        return self


class ExternalToolAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    answer: str
    tool_name: Literal["get_nbu_exchange_rate"] = TOOL_NAME
    tool_input: ExchangeRateInput
    result: ExchangeRateResult
    router_provider: str
    latency_ms: float
    notice: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class NbuRateRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    txt: str = Field(min_length=1)
    rate: Decimal = Field(gt=0)
    cc: str
    exchangedate: str
    special: Literal["Y", "N"] | None

    @field_validator("cc")
    @classmethod
    def normalize_response_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("Некоректний currency code у відповіді НБУ")
        return normalized

    def parsed_exchange_date(self) -> Date:
        try:
            return datetime.strptime(
                self.exchangedate,
                "%d.%m.%Y",
            ).date()
        except ValueError as error:
            raise ValueError(
                "Некоректний exchangedate у відповіді НБУ"
            ) from error


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
