from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


class GeneratedPayloadError(ValueError):
    """Raised when an LLM response violates the grounded JSON contract."""


@dataclass(frozen=True)
class GeneratedPayload:
    answer: str
    citations: tuple[str, ...]
    insufficient_context: bool


@dataclass(frozen=True)
class RagAnswer:
    question: str
    answer: str
    citations: tuple[str, ...]
    retrieved_chunks: tuple[dict[str, Any], ...]
    provider: str
    is_fallback: bool
    latency_ms: float
    notice: str | None = None
    retrieval_latency_ms: float = 0.0
    generation_latency_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": list(self.citations),
            "retrieved_chunks": list(self.retrieved_chunks),
            "provider": self.provider,
            "is_fallback": self.is_fallback,
            "latency_ms": self.latency_ms,
            "notice": self.notice,
            "retrieval_latency_ms": self.retrieval_latency_ms,
            "generation_latency_ms": self.generation_latency_ms,
        }


def detect_question_language(question: str) -> str:
    lowered = question.lower()

    if re.search(r"[іїєґ]", lowered):
        return "uk"
    if re.search(r"[а-яё]", lowered):
        return "ru"
    return "en"


def fallback_sentence(language: str) -> str:
    if language == "ru":
        return (
            "В предоставленном контексте недостаточно информации, "
            "чтобы ответить на этот вопрос."
        )
    if language == "en":
        return (
            "The provided context does not contain enough information "
            "to answer this question."
        )
    return (
        "У наданому контексті недостатньо інформації, "
        "щоб відповісти на це запитання."
    )


def _extract_json_object(raw_output: str) -> dict[str, Any]:
    text = raw_output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as first_error:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise GeneratedPayloadError(
                "Model output не містить JSON object"
            ) from first_error
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as error:
            raise GeneratedPayloadError(
                "Model output містить некоректний JSON"
            ) from error

    if not isinstance(payload, dict):
        raise GeneratedPayloadError("Model output повинен бути JSON object")
    return payload


def parse_generated_payload(
    raw_output: str,
    allowed_chunk_ids: set[str],
    required_fallback: str,
) -> GeneratedPayload:
    payload = _extract_json_object(raw_output)
    expected_fields = {
        "answer",
        "citations",
        "insufficient_context",
    }
    if set(payload) != expected_fields:
        raise GeneratedPayloadError(
            "JSON повинен містити тільки answer, citations "
            "та insufficient_context"
        )

    answer = payload["answer"]
    citations = payload["citations"]
    insufficient_context = payload["insufficient_context"]

    if not isinstance(answer, str) or not answer.strip():
        raise GeneratedPayloadError("answer повинен бути непорожнім рядком")
    if not isinstance(citations, list) or not all(
        isinstance(item, str) and item
        for item in citations
    ):
        raise GeneratedPayloadError("citations повинен бути списком ID")
    if not isinstance(insufficient_context, bool):
        raise GeneratedPayloadError(
            "insufficient_context повинен бути boolean"
        )

    unique_citations = tuple(dict.fromkeys(citations))
    unknown = set(unique_citations) - allowed_chunk_ids
    if unknown:
        raise GeneratedPayloadError(
            f"Model output містить невідомі citations: {sorted(unknown)}"
        )

    if insufficient_context:
        if unique_citations:
            raise GeneratedPayloadError(
                "Fallback response не повинен містити citations"
            )
        if answer.strip() != required_fallback:
            raise GeneratedPayloadError(
                "Fallback response повинен використовувати точну фразу"
            )
    elif not unique_citations:
        raise GeneratedPayloadError(
            "Grounded answer повинен містити хоча б одну citation"
        )

    return GeneratedPayload(
        answer=answer.strip(),
        citations=unique_citations,
        insufficient_context=insufficient_context,
    )


def compact_retrieved_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    metadata = chunk.get("metadata") or {}
    return {
        "chunk_id": chunk["chunk_id"],
        "source_file": chunk["source_file"],
        "section": metadata.get("section") or chunk.get("section") or "",
        "reranker_raw_score": float(
            chunk.get("reranker_raw_score", 0.0)
        ),
        "reranker_score": float(chunk.get("reranker_score", 0.0)),
        "text": chunk["text"],
    }


def format_rag_answer(result: RagAnswer) -> str:
    lines: list[str] = []
    if result.notice:
        lines.append(f"Примітка: {result.notice}")
        lines.append("")

    lines.append(result.answer)

    if result.citations:
        lines.extend(["", "Джерела:"])
        chunks_by_id = {
            chunk["chunk_id"]: chunk
            for chunk in result.retrieved_chunks
        }
        for citation in result.citations:
            chunk = chunks_by_id[citation]
            lines.append(f"- [{citation}] — {chunk['source_file']}")

    lines.extend(
        [
            "",
            f"Provider: {result.provider}",
            f"Latency: {result.latency_ms:.0f} ms",
        ]
    )
    return "\n".join(lines)
