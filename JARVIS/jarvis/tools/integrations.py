from __future__ import annotations

from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from jarvis.config import JarvisConfig
from jarvis.models import RiskLevel
from jarvis.tools.base import ToolContext, ToolExecutionError, ToolResult
from jarvis.tools.system import _validate_public_url


class WebSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=500)
    max_results: int = Field(default=5, ge=1, le=10)


def web_search_handler(config: JarvisConfig):
    def handler(value: WebSearchInput, _: ToolContext) -> ToolResult:
        if not config.web_search_api_key:
            raise ToolExecutionError("Web search API key is not configured")
        try:
            response = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": config.web_search_api_key,
                    "query": value.query,
                    "max_results": value.max_results,
                    "include_answer": False,
                    "search_depth": "basic",
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            results = [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": item.get("content"),
                    "score": item.get("score"),
                }
                for item in (payload.get("results") or [])[: value.max_results]
            ]
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise ToolExecutionError("Web search provider is temporarily unavailable") from error
        return ToolResult(
            content="\n\n".join(
                f"{item['title']}\n{item['url']}\n{item['content']}" for item in results
            ),
            data={"query": value.query, "results": results},
            source="Tavily Search API",
        )

    return handler


class WorkspaceIntegrationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal[
        "list_messages",
        "create_draft",
        "list_events",
        "create_event",
    ]
    parameters: dict = Field(default_factory=dict)


def workspace_risk(value: WorkspaceIntegrationInput, _: ToolContext) -> RiskLevel:
    return RiskLevel.READ if value.operation.startswith("list_") else RiskLevel.EXTERNAL_MUTATION


def _api_call(method: str, url: str, token: str, *, params=None, json=None) -> dict:
    try:
        response = httpx.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            json=json,
            timeout=20,
        )
        response.raise_for_status()
        return response.json() if response.content else {}
    except (httpx.HTTPError, ValueError) as error:
        raise ToolExecutionError("External workspace provider request failed") from error


def google_workspace_handler(config: JarvisConfig):
    def handler(value: WorkspaceIntegrationInput, _: ToolContext) -> ToolResult:
        token = config.google_access_token
        if not token:
            raise ToolExecutionError("Google OAuth access token is not configured")
        parameters = value.parameters
        if value.operation == "list_messages":
            data = _api_call("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages", token, params={"maxResults": min(int(parameters.get("max_results", 10)), 25)})
        elif value.operation == "create_draft":
            raw = str(parameters.get("raw_base64url", ""))
            if not raw:
                raise ToolExecutionError("create_draft requires raw_base64url")
            data = _api_call("POST", "https://gmail.googleapis.com/gmail/v1/users/me/drafts", token, json={"message": {"raw": raw}})
        elif value.operation == "list_events":
            data = _api_call("GET", "https://www.googleapis.com/calendar/v3/calendars/primary/events", token, params={"maxResults": min(int(parameters.get("max_results", 10)), 25), "singleEvents": "true", "orderBy": "startTime", "timeMin": parameters.get("time_min")})
        else:
            event = parameters.get("event")
            if not isinstance(event, dict):
                raise ToolExecutionError("create_event requires an event object")
            data = _api_call("POST", "https://www.googleapis.com/calendar/v3/calendars/primary/events", token, json=event)
        return ToolResult(content=f"Google operation completed: {value.operation}", data=data, source="Google Workspace API")
    return handler


def microsoft_workspace_handler(config: JarvisConfig):
    def handler(value: WorkspaceIntegrationInput, _: ToolContext) -> ToolResult:
        token = config.microsoft_access_token
        if not token:
            raise ToolExecutionError("Microsoft OAuth access token is not configured")
        parameters = value.parameters
        graph = "https://graph.microsoft.com/v1.0/me"
        if value.operation == "list_messages":
            data = _api_call("GET", f"{graph}/messages", token, params={"$top": min(int(parameters.get("max_results", 10)), 25), "$select": "id,subject,receivedDateTime,from"})
        elif value.operation == "create_draft":
            message = parameters.get("message")
            if not isinstance(message, dict):
                raise ToolExecutionError("create_draft requires a message object")
            data = _api_call("POST", f"{graph}/messages", token, json=message)
        elif value.operation == "list_events":
            data = _api_call("GET", f"{graph}/events", token, params={"$top": min(int(parameters.get("max_results", 10)), 25), "$select": "id,subject,start,end,location"})
        else:
            event = parameters.get("event")
            if not isinstance(event, dict):
                raise ToolExecutionError("create_event requires an event object")
            data = _api_call("POST", f"{graph}/events", token, json=event)
        return ToolResult(content=f"Microsoft operation completed: {value.operation}", data=data, source="Microsoft Graph")
    return handler


class BrowserInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["extract_text", "screenshot"]
    url: str = Field(min_length=8, max_length=4096)
    output_path: str | None = Field(default=None, max_length=32_000)


def browser_risk(value: BrowserInput, _: ToolContext) -> RiskLevel:
    return RiskLevel.READ if value.operation == "extract_text" else RiskLevel.WRITE


def browser_available() -> tuple[bool, str]:
    configured = __import__("os").getenv("PLAYWRIGHT_BROWSERS_PATH")
    cache = (
        Path(configured)
        if configured
        else Path.home() / "AppData" / "Local" / "ms-playwright"
    )
    installed = cache.exists() and any(cache.glob("chromium-*"))
    return (
        installed,
        "Chromium installed" if installed else "run: python -m playwright install chromium",
    )


def browser_automation(value: BrowserInput, context: ToolContext) -> ToolResult:
    _validate_public_url(value.url)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(value.url, wait_until="domcontentloaded", timeout=30_000)
            if value.operation == "extract_text":
                content = page.locator("body").inner_text(timeout=10_000)[:100_000]
                result = ToolResult(content=content, data={"url": page.url}, source=page.url)
            else:
                if not value.output_path:
                    raise ToolExecutionError("screenshot requires output_path")
                target = context.path_guard.validate(value.output_path, context.policy.scope, context.workspace_root).resolved_path
                target.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(target), full_page=True)
                result = ToolResult(content=f"Screenshot saved: {target}", data={"url": page.url, "path": str(target)}, source=page.url, changed_paths=[str(target)])
            browser.close()
            return result
    except ToolExecutionError:
        raise
    except Exception as error:
        raise ToolExecutionError("Controlled browser operation failed") from error


class WindowsAutomationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["list_windows", "focus_window"]
    title: str | None = Field(default=None, max_length=500)


def windows_risk(value: WindowsAutomationInput, _: ToolContext) -> RiskLevel:
    return RiskLevel.READ if value.operation == "list_windows" else RiskLevel.EXTERNAL_MUTATION


def windows_automation(value: WindowsAutomationInput, _: ToolContext) -> ToolResult:
    if __import__("os").name != "nt":
        raise ToolExecutionError("Windows UI Automation is available only on Windows")
    try:
        from pywinauto import Desktop
        windows = [
            {"title": window.window_text(), "handle": window.handle}
            for window in Desktop(backend="uia").windows()
            if window.window_text().strip()
        ]
        if value.operation == "list_windows":
            return ToolResult(content="\n".join(item["title"] for item in windows[:100]), data={"windows": windows[:100]}, source="Windows UI Automation")
        if not value.title:
            raise ToolExecutionError("focus_window requires title")
        target = Desktop(backend="uia").window(title_re=f".*{__import__('re').escape(value.title)}.*")
        target.set_focus()
        return ToolResult(content=f"Focused window: {value.title}", data={"title": value.title}, source="Windows UI Automation")
    except ToolExecutionError:
        raise
    except Exception as error:
        raise ToolExecutionError("Windows UI Automation operation failed") from error
