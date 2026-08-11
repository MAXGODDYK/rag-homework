from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class AgentMode(StrEnum):
    SAFE = "safe"
    AUTONOMOUS = "autonomous"


class FileScope(StrEnum):
    WORKSPACE = "workspace"
    ROOTS = "roots"
    COMPUTER = "computer"


class RiskLevel(StrEnum):
    READ = "read"
    CALCULATE = "calculate"
    WRITE = "write"
    EXECUTE = "execute"
    EXTERNAL_MUTATION = "external_mutation"
    HIGH_RISK = "high_risk"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    BUTTON_CONFIRMED = "button_confirmed"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    EXECUTED = "executed"


class SessionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AgentMode = AgentMode.SAFE
    scope: FileScope = FileScope.WORKSPACE
    provider_profile: Literal[
        "auto", "local-agent", "local-grounded", "remote-strong"
    ] = "auto"
    source_selector: str = "auto"


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    file_name: str
    source_path: str
    chunk_id: str
    page: int | None = None
    heading: str | None = None
    sheet: str | None = None
    cell_range: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    score: float | None = None


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any]
    rationale: str = ""


class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["tool", "final"]
    tool: ToolCallRequest | None = None
    answer: str | None = None
    grounded: bool = False
    citations: list[Citation] = Field(default_factory=list)


class AgentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    message_id: str
    answer: str
    grounded: bool
    citations: list[Citation]
    provider: str
    tool_run_ids: list[str] = Field(default_factory=list)
    pending_approval_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "chat.started",
        "chat.delta",
        "retrieval.completed",
        "tool.proposed",
        "approval.required",
        "tool.started",
        "tool.output",
        "file.changed",
        "chat.completed",
        "chat.failed",
        "job.updated",
    ]
    session_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    root_path: str | None = None


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    project_id: str | None = None
    title: str = Field(default="New conversation", max_length=200)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=100_000)


class ApprovalConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_code: str | None = Field(default=None, min_length=6, max_length=16)
