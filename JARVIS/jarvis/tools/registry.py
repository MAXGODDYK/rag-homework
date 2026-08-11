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
from jarvis.tools.integrations import (
    BrowserInput,
    WebSearchInput,
    WindowsAutomationInput,
    WorkspaceIntegrationInput,
    browser_automation,
    browser_available,
    browser_risk,
    google_workspace_handler,
    microsoft_workspace_handler,
    web_search_handler,
    windows_automation,
    windows_risk,
    workspace_risk,
)


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
    registry.register(ToolSpec(name="web_search", description="Search the public web through the configured Tavily adapter.", input_model=WebSearchInput, risk=RiskLevel.READ, handler=web_search_handler(jarvis_config), availability=lambda: (bool(jarvis_config.web_search_api_key), "configured" if jarvis_config.web_search_api_key else "WEB_SEARCH_API_KEY is not configured")))
    registry.register(ToolSpec(name="google_email_calendar", description="Read mail/calendar or create drafts/events through Google Workspace OAuth.", input_model=WorkspaceIntegrationInput, risk=RiskLevel.EXTERNAL_MUTATION, risk_resolver=workspace_risk, handler=google_workspace_handler(jarvis_config), availability=lambda: (bool(jarvis_config.google_access_token), "configured" if jarvis_config.google_access_token else "GOOGLE_ACCESS_TOKEN is not configured")))
    registry.register(ToolSpec(name="microsoft_email_calendar", description="Read mail/calendar or create drafts/events through Microsoft Graph OAuth.", input_model=WorkspaceIntegrationInput, risk=RiskLevel.EXTERNAL_MUTATION, risk_resolver=workspace_risk, handler=microsoft_workspace_handler(jarvis_config), availability=lambda: (bool(jarvis_config.microsoft_access_token), "configured" if jarvis_config.microsoft_access_token else "MICROSOFT_ACCESS_TOKEN is not configured")))
    registry.register(ToolSpec(name="browser_automation", description="Controlled headless navigation for explicit public URLs and screenshots.", input_model=BrowserInput, risk=RiskLevel.READ, risk_resolver=browser_risk, handler=browser_automation, availability=browser_available, timeout_seconds=60))
    registry.register(ToolSpec(name="windows_ui_automation", description="List or focus visible Windows application windows.", input_model=WindowsAutomationInput, risk=RiskLevel.EXTERNAL_MUTATION, risk_resolver=windows_risk, handler=windows_automation, availability=lambda: (__import__("os").name == "nt", "Windows UI Automation available" if __import__("os").name == "nt" else "Windows only")))
    return registry
