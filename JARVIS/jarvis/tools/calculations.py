from __future__ import annotations

import ast
import math
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jarvis.tools.base import ToolContext, ToolExecutionError, ToolResult


MONEY = Decimal("0.01")


class BudgetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monthly_income: Decimal = Field(gt=0, le=Decimal("100000000"))
    fixed_expenses: Decimal = Field(ge=0, le=Decimal("100000000"))
    savings_target: Decimal = Field(default=0, ge=0, le=Decimal("100000000"))
    debt_payments: Decimal = Field(default=0, ge=0, le=Decimal("100000000"))
    currency: str = Field(default="UAH", pattern=r"^[A-Za-z]{3}$")


def monthly_budget(value: BudgetInput, _: ToolContext) -> ToolResult:
    available = value.monthly_income - value.fixed_expenses - value.savings_target - value.debt_payments
    available = available.quantize(MONEY, rounding=ROUND_HALF_UP)
    status = "surplus" if available >= 0 else "deficit"
    return ToolResult(
        content=(
            f"Available monthly amount: {available} {value.currency.upper()} ({status}). "
            "This is a deterministic planning calculation, not financial advice."
        ),
        data={
            "available_amount": float(available),
            "currency": value.currency.upper(),
            "status": status,
        },
        source="deterministic monthly budget calculator",
    )


class SavingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_amount: Decimal = Field(gt=0)
    current_amount: Decimal = Field(default=0, ge=0)
    monthly_contribution: Decimal = Field(gt=0)
    annual_yield_percent: Decimal = Field(default=0, ge=0, le=100)
    currency: str = Field(default="UAH", pattern=r"^[A-Za-z]{3}$")


def savings_plan(value: SavingsInput, _: ToolContext) -> ToolResult:
    balance = value.current_amount
    monthly_rate = value.annual_yield_percent / Decimal("1200")
    months = 0
    while balance < value.target_amount and months < 1200:
        balance = balance * (Decimal("1") + monthly_rate) + value.monthly_contribution
        months += 1
    if months >= 1200 and balance < value.target_amount:
        raise ToolExecutionError("Savings target exceeds the 100-year calculation horizon")
    projected = balance.quantize(MONEY, rounding=ROUND_HALF_UP)
    return ToolResult(
        content=(
            f"Target is reached in approximately {months} month(s); projected balance "
            f"{projected} {value.currency.upper()}. This is not financial advice."
        ),
        data={"months": months, "projected_balance": float(projected), "currency": value.currency.upper()},
        source="deterministic savings calculator",
    )


class LoanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    principal: Decimal = Field(gt=0)
    annual_interest_percent: Decimal = Field(ge=0, le=200)
    term_months: int = Field(ge=1, le=1200)
    extra_monthly_payment: Decimal = Field(default=0, ge=0)
    currency: str = Field(default="UAH", pattern=r"^[A-Za-z]{3}$")


def loan_payment(value: LoanInput, _: ToolContext) -> ToolResult:
    monthly_rate = value.annual_interest_percent / Decimal("1200")
    if monthly_rate == 0:
        base_payment = value.principal / value.term_months
    else:
        factor = (Decimal("1") + monthly_rate) ** value.term_months
        base_payment = value.principal * monthly_rate * factor / (factor - Decimal("1"))
    payment = base_payment + value.extra_monthly_payment
    balance = value.principal
    total_paid = Decimal("0")
    actual_months = 0
    while balance > 0 and actual_months < value.term_months:
        interest = balance * monthly_rate
        principal_payment = max(Decimal("0"), payment - interest)
        if principal_payment <= 0:
            raise ToolExecutionError("Monthly payment does not cover accrued interest")
        paid = min(payment, balance + interest)
        balance = max(Decimal("0"), balance - principal_payment)
        total_paid += paid
        actual_months += 1
    monthly = payment.quantize(MONEY, rounding=ROUND_HALF_UP)
    total = total_paid.quantize(MONEY, rounding=ROUND_HALF_UP)
    return ToolResult(
        content=(
            f"Estimated monthly payment: {monthly} {value.currency.upper()}; "
            f"total paid: {total}; duration: {actual_months} month(s). Not financial advice."
        ),
        data={
            "monthly_payment": float(monthly),
            "total_paid": float(total),
            "actual_months": actual_months,
            "currency": value.currency.upper(),
        },
        source="deterministic amortization calculator",
    )


class StudyTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(ge=5, le=10_000)
    priority: int = Field(default=3, ge=1, le=5)
    deadline: datetime | None = None


class StudyScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tasks: list[StudyTask] = Field(min_length=1, max_length=100)
    daily_available_minutes: int = Field(ge=15, le=1440)
    session_minutes: int = Field(default=50, ge=10, le=180)
    break_minutes: int = Field(default=10, ge=0, le=60)


def study_schedule(value: StudyScheduleInput, _: ToolContext) -> ToolResult:
    ordered = sorted(value.tasks, key=lambda task: (task.deadline or datetime.max, -task.priority, task.name))
    plan: list[dict[str, object]] = []
    day = 1
    used = 0
    for task in ordered:
        remaining = task.duration_minutes
        while remaining > 0:
            duration = min(value.session_minutes, remaining)
            cost = duration + (value.break_minutes if used else 0)
            if used and used + cost > value.daily_available_minutes:
                day += 1
                used = 0
                cost = duration
            plan.append({"day": day, "task": task.name, "minutes": duration})
            used += cost
            remaining -= duration
    return ToolResult(
        content=f"Created a deterministic study plan for {day} day(s) and {len(plan)} session(s).",
        data={"days": day, "sessions": plan},
        source="deterministic study scheduler",
    )


ALLOWED_BINARY_OPERATORS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left**right,
}
ALLOWED_UNARY_OPERATORS = {ast.UAdd: lambda value: value, ast.USub: lambda value: -value}
ALLOWED_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in ALLOWED_CONSTANTS:
        return float(ALLOWED_CONSTANTS[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINARY_OPERATORS:
        return float(ALLOWED_BINARY_OPERATORS[type(node.op)](_evaluate(node.left), _evaluate(node.right)))
    if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY_OPERATORS:
        return float(ALLOWED_UNARY_OPERATORS[type(node.op)](_evaluate(node.operand)))
    raise ToolExecutionError("Expression contains a forbidden operation")


class CalculatorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1, max_length=500)


def calculate(value: CalculatorInput, _: ToolContext) -> ToolResult:
    try:
        tree = ast.parse(value.expression, mode="eval")
        answer = _evaluate(tree)
    except (SyntaxError, ZeroDivisionError, OverflowError) as error:
        raise ToolExecutionError("Invalid mathematical expression") from error
    if not math.isfinite(answer):
        raise ToolExecutionError("Expression produced a non-finite result")
    return ToolResult(content=f"Result: {answer:g}", data={"result": answer}, source="safe calculator")


UNIT_FACTORS: dict[tuple[str, str], Decimal] = {
    ("m", "km"): Decimal("0.001"),
    ("km", "m"): Decimal("1000"),
    ("g", "kg"): Decimal("0.001"),
    ("kg", "g"): Decimal("1000"),
    ("cm", "m"): Decimal("0.01"),
    ("m", "cm"): Decimal("100"),
    ("min", "h"): Decimal("0.0166666666666666667"),
    ("h", "min"): Decimal("60"),
}


class UnitConversionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Decimal
    from_unit: str = Field(min_length=1, max_length=20)
    to_unit: str = Field(min_length=1, max_length=20)


def convert_units(value: UnitConversionInput, _: ToolContext) -> ToolResult:
    source, target = value.from_unit.lower(), value.to_unit.lower()
    if source == target:
        result = value.value
    elif (source, target) in UNIT_FACTORS:
        result = value.value * UNIT_FACTORS[(source, target)]
    elif (source, target) == ("c", "f"):
        result = value.value * Decimal("1.8") + Decimal("32")
    elif (source, target) == ("f", "c"):
        result = (value.value - Decimal("32")) / Decimal("1.8")
    else:
        raise ToolExecutionError(f"Unsupported conversion: {source} -> {target}")
    rounded = result.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP).normalize()
    return ToolResult(
        content=f"{value.value} {source} = {rounded} {target}",
        data={"value": float(rounded), "unit": target},
        source="deterministic unit converter",
    )


class TimeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = Field(default="Europe/Kyiv", min_length=1, max_length=100)


def current_time(value: TimeInput, _: ToolContext) -> ToolResult:
    try:
        current = datetime.now(ZoneInfo(value.timezone))
    except ZoneInfoNotFoundError as error:
        raise ToolExecutionError(f"Unknown timezone: {value.timezone}") from error
    return ToolResult(
        content=f"Current time in {value.timezone}: {current.isoformat(timespec='seconds')}",
        data={"timezone": value.timezone, "datetime": current.isoformat()},
        source="local system clock",
    )
