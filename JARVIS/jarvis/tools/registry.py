from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from jarvis.config import JarvisConfig, load_jarvis_config
from jarvis.models import RiskLevel
from jarvis.tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec
from jarvis.tools.calculations import (
    BudgetInput,
    CalculatorInput,
    LoanInput,
    SavingsInput,
    StudyScheduleInput,
    TimeInput,
    UnitConversionInput,
    calculate,
    convert_units,
    current_time,
    loan_payment,
    monthly_budget,
    savings_plan,
    study_schedule,
)
from jarvis.tools.system import (
    ListDirectoryInput,
    PatchFileInput,
    ReadFileInput,
    ShellInput,
    UrlInput,
    WeatherInput,
    WriteFileInput,
    execute_shell,
    file_preview,
    file_write_risk,
    list_directory,
    patch_file,
    read_file,
    read_url,
    shell_preview,
    shell_risk,
    weather,
    write_file,
)
from scripts.tools.nbu_exchange import NbuExchangeRateTool
from scripts.tools.orchestrator import build_exchange_rate_answer
from scripts.tools.schemas import ExchangeRateInput


def _nbu(value: ExchangeRateInput, _: ToolContext) -> ToolResult:
    result = NbuExchangeRateTool().execute(value)
    return ToolResult(
        content=build_exchange_rate_answer(result, "uk"),
        data=result.model_dump(mode="json"),
        source=result.source_url,
    )


class IntegrationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(min_length=1, max_length=100)
    parameters: dict = Field(default_factory=dict)


def _disabled(name: str):
    def handler(_: IntegrationInput, __: ToolContext) -> ToolResult:
        raise RuntimeError(f"{name} integration is not configured")

    return handler


def build_default_registry(config: JarvisConfig | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    registrations = [
        ToolSpec(name="get_nbu_exchange_rate", description="Get an official current or historical NBU exchange rate and convert an amount to UAH.", input_model=ExchangeRateInput, risk=RiskLevel.READ, handler=_nbu),
        ToolSpec(name="calculate_monthly_budget", description="Calculate disposable monthly money from income, fixed expenses, savings and debt payments.", input_model=BudgetInput, risk=RiskLevel.CALCULATE, handler=monthly_budget),
        ToolSpec(name="calculate_savings_plan", description="Estimate months required to reach a savings target.", input_model=SavingsInput, risk=RiskLevel.CALCULATE, handler=savings_plan),
        ToolSpec(name="calculate_loan_payment", description="Calculate an amortized loan payment and total repayment.", input_model=LoanInput, risk=RiskLevel.CALCULATE, handler=loan_payment),
        ToolSpec(name="build_study_schedule", description="Build a deterministic priority/deadline-based study schedule.", input_model=StudyScheduleInput, risk=RiskLevel.CALCULATE, handler=study_schedule),
        ToolSpec(name="calculator", description="Evaluate a safe arithmetic expression without Python eval.", input_model=CalculatorInput, risk=RiskLevel.CALCULATE, handler=calculate),
        ToolSpec(name="convert_units", description="Convert supported length, mass, time or temperature units.", input_model=UnitConversionInput, risk=RiskLevel.CALCULATE, handler=convert_units),
        ToolSpec(name="current_time", description="Return the current local time in an IANA timezone.", input_model=TimeInput, risk=RiskLevel.READ, handler=current_time),
        ToolSpec(name="weather", description="Get current weather for a named location from Open-Meteo.", input_model=WeatherInput, risk=RiskLevel.READ, handler=weather),
        ToolSpec(name="read_url", description="Read an explicit public HTTP(S) text page with SSRF protection.", input_model=UrlInput, risk=RiskLevel.READ, handler=read_url),
        ToolSpec(name="list_directory", description="List files inside the selected filesystem scope.", input_model=ListDirectoryInput, risk=RiskLevel.READ, handler=list_directory),
        ToolSpec(name="read_file", description="Read a UTF-8 text file with line boundaries.", input_model=ReadFileInput, risk=RiskLevel.READ, handler=read_file),
        ToolSpec(name="write_file", description="Create or overwrite a text file inside the selected scope.", input_model=WriteFileInput, risk=RiskLevel.WRITE, handler=write_file, risk_resolver=file_write_risk, preview_builder=file_preview),
        ToolSpec(name="patch_file", description="Apply an exact guarded text replacement to a file.", input_model=PatchFileInput, risk=RiskLevel.WRITE, handler=patch_file, risk_resolver=file_write_risk, preview_builder=file_preview),
        ToolSpec(name="execute_shell", description="Execute an argument-vector command with cwd, timeout and output limits.", input_model=ShellInput, risk=RiskLevel.EXECUTE, handler=execute_shell, risk_resolver=shell_risk, preview_builder=shell_preview, timeout_seconds=300),
    ]
    for registration in registrations:
        registry.register(registration)

    jarvis_config = config or load_jarvis_config()
    integrations = [
        ("web_search", bool(jarvis_config.web_search_api_key)),
        ("google_email_calendar", bool(jarvis_config.google_client_id and jarvis_config.google_client_secret)),
        ("microsoft_email_calendar", bool(jarvis_config.microsoft_client_id)),
        ("browser_automation", False),
        ("windows_ui_automation", False),
    ]
    for name, enabled in integrations:
        registry.register(
            ToolSpec(
                name=name,
                description=f"Optional {name.replace('_', ' ')} integration.",
                input_model=IntegrationInput,
                risk=RiskLevel.EXTERNAL_MUTATION,
                handler=_disabled(name),
                availability=lambda enabled=False, name=name: (
                    enabled,
                    f"{name} adapter is not enabled in this build",
                ),
            )
        )
    return registry
