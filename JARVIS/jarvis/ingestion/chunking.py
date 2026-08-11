from __future__ import annotations

import re
from hashlib import sha256

from .models import ChunkRecord, ExtractedUnit


def _stable_id(document_id: str, ordinal: int, text: str) -> str:
    digest = sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{document_id}_chunk_{ordinal:05d}_{digest}"


def chunk_units(
    document_id: str,
    units: list[ExtractedUnit],
    target_characters: int = 1200,
    overlap_characters: int = 180,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    ordinal = 0
    for unit in units:
        text = re.sub(r"[ \t]+", " ", unit.text).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(len(text), start + target_characters)
            if end < len(text):
                boundary = max(
                    text.rfind("\n", start + target_characters // 2, end),
                    text.rfind(". ", start + target_characters // 2, end),
                    text.rfind("; ", start + target_characters // 2, end),
                )
                if boundary > start:
                    end = boundary + 1
            chunk_text = text[start:end].strip()
            if chunk_text:
                ordinal += 1
                chunks.append(
                    ChunkRecord(
                        chunk_id=_stable_id(document_id, ordinal, chunk_text),
                        text=chunk_text,
                        ordinal=ordinal,
                        page=unit.page,
                        heading=unit.heading,
                        sheet=unit.sheet,
                        cell_range=unit.cell_range,
                        line_start=unit.line_start,
                        line_end=unit.line_end,
                        metadata=unit.metadata,
                    )
                )
            if end >= len(text):
                break
            start = max(start + 1, end - overlap_characters)
    return chunks


def chunk_code(
    document_id: str,
    text: str,
    target_lines: int = 80,
    overlap_lines: int = 10,
) -> list[ChunkRecord]:
    lines = text.splitlines()
    chunks: list[ChunkRecord] = []
    ordinal = 0
    start = 0
    while start < len(lines):
        end = min(len(lines), start + target_lines)
        chunk_text = "\n".join(lines[start:end]).strip()
        if chunk_text:
            ordinal += 1
            chunks.append(
                ChunkRecord(
                    chunk_id=_stable_id(document_id, ordinal, chunk_text),
                    text=chunk_text,
                    ordinal=ordinal,
                    line_start=start + 1,
                    line_end=end,
                    metadata={"kind": "code"},
                )
            )
        if end >= len(lines):
            break
        start = max(start + 1, end - overlap_lines)
    return chunks
