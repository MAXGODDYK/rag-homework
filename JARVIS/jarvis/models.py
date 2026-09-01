from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class SessionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_profile: Literal[
        "local", "extractive"
    ] = "local"
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


class RagAnswer(BaseModel):
    """Grounded answer returned by the desktop-only RAG service."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    message_id: str
    answer: str
    grounded: bool
    citations: list[Citation] = Field(default_factory=list)
    provider: str
    fallback: bool = False
    source_selector: str = "auto"
    retrieved_chunks: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "chat.started",
        "chat.delta",
        "retrieval.completed",
        "file.changed",
        "chat.completed",
        "chat.failed",
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


class LocalSettingsUpdate(BaseModel):
    """Write-only local settings accepted from the owner desktop interface."""

    model_config = ConfigDict(extra="forbid")

    ollama_model: str | None = Field(default=None, min_length=1, max_length=256)
