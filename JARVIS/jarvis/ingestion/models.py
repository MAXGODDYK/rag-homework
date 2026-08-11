from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ExtractedUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    page: int | None = None
    heading: str | None = None
    sheet: str | None = None
    cell_range: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    metadata: dict = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    path: Path
    media_type: str
    language: str | None = None
    units: list[ExtractedUnit]
    metadata: dict = Field(default_factory=dict)


class ChunkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    text: str
    ordinal: int
    page: int | None = None
    heading: str | None = None
    sheet: str | None = None
    cell_range: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    metadata: dict = Field(default_factory=dict)


class SymbolRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str
    qualified_name: str | None = None
    line_start: int
    line_end: int
    metadata: dict = Field(default_factory=dict)


class GraphEdgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_ref: str
    edge_type: str
    metadata: dict = Field(default_factory=dict)
