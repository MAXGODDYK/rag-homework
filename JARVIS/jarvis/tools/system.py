from __future__ import annotations

import ipaddress
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, field_validator

from jarvis.models import FileScope, RiskLevel
from jarvis.tools.base import ToolContext, ToolExecutionError, ToolResult


MAX_TEXT_OUTPUT = 100_000
ALLOWED_EXECUTABLES = frozenset(
    {
        "cargo",
        "dotnet",
        "git",
        "node",
        "npm",
        "npx",
        "py",
        "pytest",
        "python",
        "rg",
        "rustc",
    }
)
HIGH_RISK_EXECUTABLES = frozenset({"cmd", "powershell", "pwsh", "reg", "sc"})


class PathInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=32_000)


class ListDirectoryInput(PathInput):
    recursive: bool = False
    max_entries: int = Field(default=500, ge=1, le=10_000)


def list_directory(value: ListDirectoryInput, context: ToolContext) -> ToolResult:
    decision = context.path_guard.validate(value.path, context.policy.scope, context.workspace_root)
    path = decision.resolved_path
    if not path.is_dir():
        raise ToolExecutionError(f"Directory does not exist: {path}")
    iterator = path.rglob("*") if value.recursive else path.iterdir()
    entries: list[dict[str, object]] = []
    for entry in iterator:
        if len(entries) >= value.max_entries:
            break
        try:
            stat = entry.stat()
        except OSError:
            continue
        entries.append(
            {
                "path": str(entry),
                "relative_path": str(entry.relative_to(path)),
                "type": "directory" if entry.is_dir() else "file",
                "size_bytes": 0 if entry.is_dir() else stat.st_size,
            }
        )
    return ToolResult(
        content=f"Listed {len(entries)} entries in {path}",
        data={"root": str(path), "entries": entries, "truncated": len(entries) >= value.max_entries},
        source=str(path),
    )


class ReadFileInput(PathInput):
    line_start: int = Field(default=1, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    max_characters: int = Field(default=50_000, ge=1, le=MAX_TEXT_OUTPUT)


def read_file(value: ReadFileInput, context: ToolContext) -> ToolResult:
    decision = context.path_guard.validate(value.path, context.policy.scope, context.workspace_root)
    if decision.sensitive:
        raise ToolExecutionError("Sensitive file requires the high-risk read workflow")
    path = decision.resolved_path
    if not path.is_file():
        raise ToolExecutionError(f"File does not exist: {path}")
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ToolExecutionError("Direct file read is limited to 10 MB")
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        raise ToolExecutionError("Binary files cannot be returned as text")
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    end = min(value.line_end or len(lines), len(lines))
    selected = "\n".join(lines[value.line_start - 1 : end])[: value.max_characters]
    return ToolResult(
        content=selected,
        data={
            "path": str(path),
            "line_start": value.line_start,
            "line_end": end,
            "truncated": len(selected) >= value.max_characters,
        },
        source=str(path),
    )


class WriteFileInput(PathInput):
    content: str = Field(max_length=1_000_000)
    overwrite: bool = False


def write_file(value: WriteFileInput, context: ToolContext) -> ToolResult:
    decision = context.path_guard.validate(value.path, context.policy.scope, context.workspace_root)
    path = decision.resolved_path
    if path.exists() and not value.overwrite:
        raise ToolExecutionError("Target exists; overwrite=true is required")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.content, encoding="utf-8")
    return ToolResult(
        content=f"Wrote {len(value.content)} characters to {path}",
        data={"path": str(path), "characters": len(value.content)},
        source=str(path),
        changed_paths=[str(path)],
    )


class PatchFileInput(PathInput):
    old_text: str = Field(min_length=1, max_length=500_000)
    new_text: str = Field(max_length=500_000)
    expected_replacements: int = Field(default=1, ge=1, le=100)


def patch_file(value: PatchFileInput, context: ToolContext) -> ToolResult:
    decision = context.path_guard.validate(value.path, context.policy.scope, context.workspace_root)
    path = decision.resolved_path
    if not path.is_file():
        raise ToolExecutionError(f"File does not exist: {path}")
    original = path.read_text(encoding="utf-8")
    count = original.count(value.old_text)
    if count != value.expected_replacements:
        raise ToolExecutionError(
            f"Patch expected {value.expected_replacements} replacement(s), found {count}"
        )
    updated = original.replace(value.old_text, value.new_text)
    path.write_text(updated, encoding="utf-8")
    return ToolResult(
        content=f"Patched {path}: {count} replacement(s)",
        data={"path": str(path), "replacements": count},
        source=str(path),
        changed_paths=[str(path)],
    )


def file_write_risk(value: BaseModel, context: ToolContext) -> RiskLevel:
    raw_path = getattr(value, "path")
    decision = context.path_guard.validate(raw_path, context.policy.scope, context.workspace_root)
    return RiskLevel.HIGH_RISK if decision.sensitive else RiskLevel.WRITE


def file_preview(value: BaseModel, context: ToolContext) -> str:
    raw_path = getattr(value, "path")
    decision = context.path_guard.validate(raw_path, context.policy.scope, context.workspace_root)
    return f"Modify file: {decision.resolved_path}\nArguments: {value.model_dump(mode='json')}"


class ShellInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executable: str = Field(min_length=1, max_length=128)
    arguments: list[str] = Field(default_factory=list, max_length=100)
    cwd: str | None = Field(default=None, max_length=32_000)
    timeout_seconds: int = Field(default=30, ge=1, le=300)

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, values: list[str]) -> list[str]:
        if any(len(item) > 10_000 or "\x00" in item for item in values):
            raise ValueError("Invalid shell argument")
        return values


def shell_risk(value: ShellInput, context: ToolContext) -> RiskLevel:
    executable = Path(value.executable).stem.lower()
    if executable in HIGH_RISK_EXECUTABLES:
        return RiskLevel.HIGH_RISK
    if executable not in ALLOWED_EXECUTABLES:
        return RiskLevel.HIGH_RISK
    if value.cwd:
        decision = context.path_guard.validate(value.cwd, context.policy.scope, context.workspace_root)
        if decision.sensitive:
            return RiskLevel.HIGH_RISK
    return RiskLevel.EXECUTE


def shell_preview(value: ShellInput, context: ToolContext) -> str:
    cwd = value.cwd or (str(context.workspace_root) if context.workspace_root else os.getcwd())
    return f"Execute in {cwd}: {[value.executable, *value.arguments]}"


def execute_shell(value: ShellInput, context: ToolContext) -> ToolResult:
    risk = shell_risk(value, context)
    executable_name = Path(value.executable).stem.lower()
    if risk == RiskLevel.HIGH_RISK and executable_name not in HIGH_RISK_EXECUTABLES:
        raise ToolExecutionError(f"Executable is not in the ordinary allowlist: {value.executable}")
    executable = shutil.which(value.executable)
    if executable is None:
        raise ToolExecutionError(f"Executable not found: {value.executable}")
    cwd = context.workspace_root
    if value.cwd:
        cwd = context.path_guard.validate(value.cwd, context.policy.scope, context.workspace_root).resolved_path
    if cwd is None:
        raise ToolExecutionError("Shell execution requires an explicit cwd or workspace")
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        process = subprocess.run(
            [executable, *value.arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=value.timeout_seconds,
            creationflags=creation_flags,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ToolExecutionError("Command exceeded its timeout") from error
    stdout = process.stdout[:MAX_TEXT_OUTPUT]
    stderr = process.stderr[:MAX_TEXT_OUTPUT]
    return ToolResult(
        content=f"Exit code: {process.returncode}\n{stdout}\n{stderr}".strip(),
        data={
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": len(process.stdout) > MAX_TEXT_OUTPUT or len(process.stderr) > MAX_TEXT_OUTPUT,
        },
        source=str(cwd),
    )


class UrlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=8, max_length=4096)
    max_characters: int = Field(default=50_000, ge=100, le=MAX_TEXT_OUTPUT)


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ToolExecutionError("Only explicit HTTP(S) URLs are supported")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as error:
        raise ToolExecutionError("URL host could not be resolved") from error
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ToolExecutionError("Private, local and reserved network addresses are blocked")


def read_url(value: UrlInput, _: ToolContext) -> ToolResult:
    url = value.url
    _validate_public_url(url)
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        for _redirect in range(5):
            response = client.get(url, headers={"User-Agent": "JARVIS/0.1 explicit-url-reader"})
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ToolExecutionError("Redirect response omitted Location")
                url = urljoin(url, location)
                _validate_public_url(url)
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                raise ToolExecutionError(f"URL returned HTTP {response.status_code}") from error
            content_type = response.headers.get("content-type", "").lower()
            if not any(item in content_type for item in ("text/", "json", "xml", "html")):
                raise ToolExecutionError("URL did not return a supported text content type")
            text = response.text
            if "html" in content_type:
                soup = BeautifulSoup(text, "html.parser")
                for element in soup(["script", "style", "noscript"]):
                    element.decompose()
                text = "\n".join(soup.stripped_strings)
            text = text[: value.max_characters]
            return ToolResult(
                content=text,
                data={"url": url, "content_type": content_type, "characters": len(text)},
                source=url,
            )
    raise ToolExecutionError("URL exceeded the redirect limit")


class WeatherInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location: str = Field(min_length=2, max_length=200)


def weather(value: WeatherInput, _: ToolContext) -> ToolResult:
    try:
        with httpx.Client(timeout=10) as client:
            geocoding = client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": value.location, "count": 1, "language": "en", "format": "json"},
            )
            geocoding.raise_for_status()
            matches = geocoding.json().get("results") or []
            if not matches:
                raise ToolExecutionError(f"Location not found: {value.location}")
            place = matches[0]
            forecast = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
                    "timezone": "auto",
                },
            )
            forecast.raise_for_status()
            current = forecast.json()["current"]
    except httpx.HTTPError as error:
        raise ToolExecutionError("Weather provider is temporarily unavailable") from error
    name = ", ".join(filter(None, [place.get("name"), place.get("admin1"), place.get("country")]))
    return ToolResult(
        content=(
            f"Current weather in {name}: {current['temperature_2m']} °C, feels like "
            f"{current['apparent_temperature']} °C, wind {current['wind_speed_10m']} km/h."
        ),
        data={"location": name, "current": current},
        source="Open-Meteo",
    )
