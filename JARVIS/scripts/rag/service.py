from __future__ import annotations

from time import perf_counter
from typing import Any

from config.settings import Settings, load_settings

from .prompt_builder import build_grounded_prompt, build_repair_prompt
from .providers import (
    ProviderError,
    TextProvider,
    build_text_providers,
)
from .retriever import GroundedRetriever
from .schemas import (
    GeneratedPayloadError,
    RagAnswer,
    compact_retrieved_chunk,
    detect_question_language,
    fallback_sentence,
    parse_generated_payload,
)


class RagAnswerService:
    def __init__(
        self,
        settings: Settings | None = None,
        retriever: Any | None = None,
        providers: dict[str, TextProvider] | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.retriever = retriever or GroundedRetriever()
        self.providers: dict[str, TextProvider] = (
            providers or build_text_providers(self.settings)
        )

    def provider_status(self) -> dict[str, dict[str, Any]]:
        status: dict[str, dict[str, Any]] = {}
        for name, provider in self.providers.items():
            available, reason = provider.availability()
            status[name] = {
                "available": available,
                "reason": reason,
            }
        return status

    def _fallback_result(
        self,
        question: str,
        chunks: list[dict[str, Any]],
        started_at: float,
        retrieval_latency_ms: float,
        provider: str,
        notice: str | None = None,
    ) -> RagAnswer:
        language = detect_question_language(question)
        return RagAnswer(
            question=question,
            answer=fallback_sentence(language),
            citations=(),
            retrieved_chunks=tuple(
                compact_retrieved_chunk(chunk)
                for chunk in chunks
            ),
            provider=provider,
            is_fallback=True,
            latency_ms=(perf_counter() - started_at) * 1000,
            notice=notice,
            retrieval_latency_ms=retrieval_latency_ms,
            generation_latency_ms=0.0,
        )

    def _generate_validated(
        self,
        provider: TextProvider,
        question: str,
        chunks: list[dict[str, Any]],
        fallback: str,
    ):
        prompt = build_grounded_prompt(question, chunks, fallback)
        raw_output = provider.generate(prompt)
        allowed_ids = {chunk["chunk_id"] for chunk in chunks}

        try:
            return parse_generated_payload(
                raw_output,
                allowed_ids,
                fallback,
            )
        except GeneratedPayloadError:
            repair_prompt = build_repair_prompt(
                raw_output,
                chunks,
                fallback,
            )
            repaired_output = provider.generate(repair_prompt)
            return parse_generated_payload(
                repaired_output,
                allowed_ids,
                fallback,
            )

    def answer(
        self,
        question: str,
        provider_name: str = "openai",
        top_k: int | None = None,
        candidate_k: int | None = None,
        source_file: str | None = None,
        allow_local_fallback: bool = True,
    ) -> RagAnswer:
        started_at = perf_counter()
        question = question.strip()
        if not question:
            raise ValueError("Question не може бути порожнім")
        if len(question) > self.settings.maximum_question_length:
            raise ValueError(
                "Question перевищує максимальну довжину "
                f"{self.settings.maximum_question_length} символів"
            )
        if provider_name not in self.providers:
            raise ValueError(f"Невідомий provider: {provider_name}")

        top_k = top_k or self.settings.default_top_k
        candidate_k = candidate_k or self.settings.default_candidate_k
        if top_k < 1:
            raise ValueError("top-k повинен бути не менше 1")
        if candidate_k < top_k:
            raise ValueError("candidate-k повинен бути не менше top-k")

        retrieval_started = perf_counter()
        chunks = self.retriever.retrieve(
            question=question,
            top_k=top_k,
            candidate_k=candidate_k,
            source_file=source_file,
        )
        retrieval_latency_ms = (
            perf_counter() - retrieval_started
        ) * 1000

        if not chunks:
            return self._fallback_result(
                question,
                chunks,
                started_at,
                retrieval_latency_ms,
                provider_name,
            )

        best_raw_score = max(
            float(chunk.get("reranker_raw_score", 0.0))
            for chunk in chunks
        )
        if best_raw_score < self.settings.minimum_reranker_raw_score:
            return self._fallback_result(
                question,
                chunks,
                started_at,
                retrieval_latency_ms,
                provider_name,
                notice=(
                    "Контекст відхилено confidence gate "
                    f"({best_raw_score:.4f} < "
                    f"{self.settings.minimum_reranker_raw_score:.4f})."
                ),
            )

        language = detect_question_language(question)
        fallback = fallback_sentence(language)
        selected_provider = self.providers[provider_name]
        actual_provider_name = provider_name
        notice: str | None = None
        generation_started = perf_counter()

        try:
            payload = self._generate_validated(
                selected_provider,
                question,
                chunks,
                fallback,
            )
        except ProviderError as first_error:
            if (
                provider_name not in {"openai", "freemodel"}
                or not allow_local_fallback
            ):
                raise

            local_provider = self.providers["local"]
            available, reason = local_provider.availability()
            if not available:
                raise ProviderError(
                    f"{first_error}; local fallback недоступний: {reason}"
                ) from first_error

            payload = self._generate_validated(
                local_provider,
                question,
                chunks,
                fallback,
            )
            actual_provider_name = "local"
            notice = (
                f"{provider_name} недоступний; відповідь створено "
                "локальною Qwen."
            )
        except GeneratedPayloadError:
            return self._fallback_result(
                question,
                chunks,
                started_at,
                retrieval_latency_ms,
                provider_name,
                notice=(
                    "Model output двічі порушив JSON/citation contract."
                ),
            )

        generation_latency_ms = (
            perf_counter() - generation_started
        ) * 1000
        compact_chunks = tuple(
            compact_retrieved_chunk(chunk)
            for chunk in chunks
        )

        if payload.insufficient_context:
            answer = fallback
            citations: tuple[str, ...] = ()
        else:
            answer = payload.answer
            citations = payload.citations

        return RagAnswer(
            question=question,
            answer=answer,
            citations=citations,
            retrieved_chunks=compact_chunks,
            provider=actual_provider_name,
            is_fallback=payload.insufficient_context,
            latency_ms=(perf_counter() - started_at) * 1000,
            notice=notice,
            retrieval_latency_ms=retrieval_latency_ms,
            generation_latency_ms=generation_latency_ms,
        )
