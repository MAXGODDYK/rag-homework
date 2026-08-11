from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jarvis.models import RiskLevel, SessionPolicy
from jarvis.security import PathGuard


InputModel = TypeVar("InputModel", bound=BaseModel)


class ToolExecutionError(RuntimeError):
    """Safe failure from a registered tool."""


class ToolContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    user_id: str
    session_id: str
    project_id: str | None = None
    workspace_root: Path | None = None
    policy: SessionPolicy
    path_guard: PathGuard


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    data: dict[str, Any]
    source: str | None = None
    changed_paths: list[str] = Field(default_factory=list)
    notice: str | None = None


RiskResolver = Callable[[BaseModel, ToolContext], RiskLevel]
PreviewBuilder = Callable[[BaseModel, ToolContext], str]
ToolHandler = Callable[[BaseModel, ToolContext], ToolResult]
Availability = Callable[[], tuple[bool, str]]


class ToolSpec(Generic[InputModel]):
    def __init__(
        self,
        *,
        name: str,
        description: str,
        input_model: type[InputModel],
        risk: RiskLevel,
        handler: ToolHandler,
        scopes: frozenset[str] = frozenset({"workspace", "roots", "computer"}),
        timeout_seconds: int = 30,
        risk_resolver: RiskResolver | None = None,
        preview_builder: PreviewBuilder | None = None,
        availability: Availability | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.input_model = input_model
        self.risk = risk
        self.handler = handler
        self.scopes = scopes
        self.timeout_seconds = timeout_seconds
        self.risk_resolver = risk_resolver
        self.preview_builder = preview_builder
        self.availability = availability or (lambda: (True, "available"))

    def validate(self, arguments: dict[str, Any]) -> InputModel:
        try:
            return self.input_model.model_validate(arguments)
        except ValidationError as error:
            raise ToolExecutionError(
                f"Invalid arguments for {self.name}: {error.error_count()} validation error(s)"
            ) from error

    def effective_risk(self, arguments: InputModel, context: ToolContext) -> RiskLevel:
        return self.risk_resolver(arguments, context) if self.risk_resolver else self.risk

    def preview(self, arguments: InputModel, context: ToolContext) -> str:
        if self.preview_builder:
            return self.preview_builder(arguments, context)
        return f"{self.name}: {arguments.model_dump(mode='json')}"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec[Any]] = {}

    def register(self, spec: ToolSpec[Any]) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Duplicate tool: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec[Any]:
        try:
            return self._tools[name]
        except KeyError as error:
            raise ToolExecutionError(f"Tool is not allowlisted: {name}") from error

    def catalog(self) -> list[dict[str, Any]]:
        catalog: list[dict[str, Any]] = []
        for name in sorted(self._tools):
            spec = self._tools[name]
            available, reason = spec.availability()
            catalog.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "input_schema": spec.input_model.model_json_schema(),
                    "risk": spec.risk.value,
                    "available": available,
                    "availability_reason": reason,
                }
            )
        return catalog

    def names(self) -> frozenset[str]:
        return frozenset(self._tools)
