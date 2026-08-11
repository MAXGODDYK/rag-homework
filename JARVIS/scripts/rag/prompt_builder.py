from __future__ import annotations

from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = PROJECT_ROOT / "prompts"


def _load_template(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template не знайдено: {path}")
    return path.read_text(encoding="utf-8").strip()


def build_context(chunks: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for rank, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata") or {}
        section = metadata.get("section") or chunk.get("section") or ""
        blocks.append(
            "\n".join(
                [
                    f"[CONTEXT {rank}]",
                    f"chunk_id: {chunk['chunk_id']}",
                    f"source_file: {chunk['source_file']}",
                    f"section: {section}",
                    "text:",
                    str(chunk["text"]).strip(),
                    f"[/CONTEXT {rank}]",
                ]
            )
        )
    return "\n\n".join(blocks)


def build_grounded_prompt(
    question: str,
    chunks: list[dict[str, Any]],
    fallback: str,
) -> str:
    template = _load_template("grounded_qa_prompt.txt")
    allowed_ids = ", ".join(chunk["chunk_id"] for chunk in chunks)
    return (
        template.replace("{{QUESTION}}", question.strip())
        .replace("{{CONTEXT}}", build_context(chunks))
        .replace("{{ALLOWED_CHUNK_IDS}}", allowed_ids)
        .replace("{{FALLBACK}}", fallback)
    )


def build_repair_prompt(
    invalid_output: str,
    chunks: list[dict[str, Any]],
    fallback: str,
) -> str:
    template = _load_template("repair_prompt.txt")
    allowed_ids = ", ".join(chunk["chunk_id"] for chunk in chunks)
    return (
        template.replace("{{INVALID_OUTPUT}}", invalid_output.strip())
        .replace("{{ALLOWED_CHUNK_IDS}}", allowed_ids)
        .replace("{{FALLBACK}}", fallback)
    )
