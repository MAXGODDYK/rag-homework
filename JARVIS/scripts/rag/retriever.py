from __future__ import annotations

from threading import Lock
from typing import Any

from scripts.retrieval_improved import (
    BGE_RERANKER_MODEL_NAME,
    RetrievalPipeline,
    load_pipeline,
)


class GroundedRetriever:
    def __init__(self) -> None:
        self._pipeline: RetrievalPipeline | None = None
        self._load_lock = Lock()

    def _get_pipeline(self) -> RetrievalPipeline:
        if self._pipeline is not None:
            return self._pipeline

        with self._load_lock:
            if self._pipeline is None:
                pipeline, _, _ = load_pipeline(
                    load_reranker=True,
                    reranker_model_name=BGE_RERANKER_MODEL_NAME,
                )
                self._pipeline = pipeline
        return self._pipeline

    def retrieve(
        self,
        question: str,
        top_k: int,
        candidate_k: int,
        source_file: str | None = None,
    ) -> list[dict[str, Any]]:
        pipeline = self._get_pipeline()
        positions = pipeline.positions_for_source(source_file)
        return pipeline.reranked_search(
            query=question,
            top_k=top_k,
            candidate_k=candidate_k,
            positions=positions,
        )
