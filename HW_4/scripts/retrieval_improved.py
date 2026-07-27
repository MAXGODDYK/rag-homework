from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

try:
    from .build_index import load_chunks
    from .retrieval import (
        load_faiss_index,
        load_manifest,
        print_section,
        validate_artifacts,
    )
except ImportError:
    from build_index import load_chunks
    from retrieval import (
        load_faiss_index,
        load_manifest,
        print_section,
        validate_artifacts,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"
EMBEDDINGS_PATH = PROJECT_ROOT / "index" / "embeddings.npy"
INDEX_PATH = PROJECT_ROOT / "index" / "faiss.index"
MANIFEST_PATH = PROJECT_ROOT / "index" / "manifest.json"

BGE_RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
QWEN_RERANKER_MODEL_NAME = "Qwen/Qwen3-Reranker-4B"
RERANKER_MODELS = {
    "bge": BGE_RERANKER_MODEL_NAME,
    "qwen3-4b": QWEN_RERANKER_MODEL_NAME,
}
DEFAULT_RERANKER_KEY = "bge"
RERANKER_MODEL_NAME = RERANKER_MODELS[DEFAULT_RERANKER_KEY]
QWEN_RERANKER_PROMPT = (
    "Given a Ukrainian student-planning query, retrieve passages "
    "that directly answer the query."
)
SEMANTIC_WEIGHT = 0.75
BM25_WEIGHT = 0.25
DEFAULT_TOP_K = 3
DEFAULT_CANDIDATE_K = 10

STOPWORDS = {
    "але",
    "без",
    "був",
    "була",
    "були",
    "бути",
    "вас",
    "ви",
    "від",
    "він",
    "вона",
    "вони",
    "для",
    "до",
    "його",
    "із",
    "коли",
    "між",
    "може",
    "на",
    "під",
    "про",
    "так",
    "та",
    "це",
    "цей",
    "чи",
    "що",
    "щоб",
    "як",
}


def load_embeddings(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Embeddings не знайдено: {path}")

    embeddings = np.load(path, allow_pickle=False)

    if embeddings.ndim != 2:
        raise ValueError(
            f"Embeddings повинні мати 2 виміри: {embeddings.shape}"
        )

    if embeddings.dtype != np.float32:
        raise ValueError(
            f"Embeddings повинні мати тип float32: {embeddings.dtype}"
        )

    if not np.isfinite(embeddings).all():
        raise ValueError("Embeddings містять NaN або infinity")

    return embeddings


def validate_embeddings(
    embeddings: np.ndarray,
    chunks: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    if embeddings.shape[0] != len(chunks):
        raise ValueError("Кількість embeddings не відповідає chunks")

    if embeddings.shape[1] != manifest["embedding_dimension"]:
        raise ValueError("Розмірність embeddings не відповідає manifest")

    norms = np.linalg.norm(embeddings, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-4):
        raise ValueError("Embeddings повинні бути L2-нормалізовані")


def filter_chunk_positions(
    chunks: list[dict[str, Any]],
    source_file: str | None,
) -> list[int]:
    if source_file is None:
        return list(range(len(chunks)))

    available_sources = sorted(
        {chunk["source_file"] for chunk in chunks}
    )

    if source_file not in available_sources:
        raise ValueError(
            f"Невідомий source_file: {source_file}. "
            f"Доступні: {available_sources}"
        )

    positions = [
        position
        for position, chunk in enumerate(chunks)
        if chunk["source_file"] == source_file
    ]

    if not positions:
        raise ValueError("Після metadata filtering не залишилось chunks")

    return positions


def validate_search_parameters(
    query: str,
    top_k: int,
    candidate_k: int | None = None,
) -> str:
    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("Query не може бути порожнім")

    if top_k < 1:
        raise ValueError("top-k повинен бути не менше 1")

    if candidate_k is not None:
        if candidate_k < 1:
            raise ValueError("candidate-k повинен бути не менше 1")
        if candidate_k < top_k:
            raise ValueError("candidate-k повинен бути не менше top-k")

    return normalized_query


def tokenize(text: str) -> list[str]:
    tokens = re.findall(
        r"[^\W_]+",
        text.lower(),
        flags=re.UNICODE,
    )

    return [
        token
        for token in tokens
        if len(token) >= 3 and token not in STOPWORDS
    ]


def min_max_normalize(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)

    if array.ndim != 1:
        raise ValueError("Для min-max normalization очікується 1D масив")

    if array.size == 0:
        return array.copy()

    if not np.isfinite(array).all():
        raise ValueError("Scores містять NaN або infinity")

    minimum = float(array.min())
    maximum = float(array.max())

    if np.isclose(minimum, maximum):
        return np.zeros_like(array, dtype=np.float32)

    return ((array - minimum) / (maximum - minimum)).astype(
        np.float32
    )


def _result_from_chunk(
    chunk: dict[str, Any],
    position: int,
    **scores: float,
) -> dict[str, Any]:
    return {
        "position": position,
        "chunk_id": chunk["chunk_id"],
        "document_id": chunk["document_id"],
        "source_file": chunk["source_file"],
        "text": chunk["text"],
        "metadata": chunk["metadata"],
        **scores,
    }


class RetrievalPipeline:
    def __init__(
        self,
        chunks: list[dict[str, Any]],
        embeddings: np.ndarray,
        embedding_model: SentenceTransformer,
        reranker_model: CrossEncoder | None = None,
    ) -> None:
        self.chunks = chunks
        self.embeddings = embeddings
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model

    def positions_for_source(self, source_file: str | None) -> list[int]:
        return filter_chunk_positions(self.chunks, source_file)

    def _query_embedding(self, query: str) -> np.ndarray:
        query_embedding = self.embedding_model.encode(
            [query],
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)

        if query_embedding.ndim != 2 or query_embedding.shape[0] != 1:
            raise ValueError(
                "Embedding моделі повернув неочікувану форму: "
                f"{query_embedding.shape}"
            )

        faiss.normalize_L2(query_embedding)
        return query_embedding[0]

    def semantic_search(
        self,
        query: str,
        top_k: int,
        positions: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        query = validate_search_parameters(query, top_k)
        candidate_positions = (
            positions
            if positions is not None
            else list(range(len(self.chunks)))
        )

        if not candidate_positions:
            raise ValueError("Search space не містить chunks")

        query_embedding = self._query_embedding(query)
        semantic_scores = (
            self.embeddings[candidate_positions] @ query_embedding
        ).astype(np.float32)
        semantic_normalized = min_max_normalize(semantic_scores)

        results = [
            _result_from_chunk(
                self.chunks[position],
                position,
                semantic_score=float(semantic_scores[local_position]),
                semantic_normalized=float(
                    semantic_normalized[local_position]
                ),
            )
            for local_position, position in enumerate(candidate_positions)
        ]
        results.sort(
            key=lambda item: (
                item["semantic_score"],
                item["chunk_id"],
            ),
            reverse=True,
        )
        return results[: min(top_k, len(results))]

    def hybrid_search(
        self,
        query: str,
        top_k: int,
        positions: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        query = validate_search_parameters(query, top_k)
        candidate_positions = (
            positions
            if positions is not None
            else list(range(len(self.chunks)))
        )

        if not candidate_positions:
            raise ValueError("Search space не містить chunks")

        query_embedding = self._query_embedding(query)
        semantic_scores = (
            self.embeddings[candidate_positions] @ query_embedding
        ).astype(np.float32)
        semantic_normalized = min_max_normalize(semantic_scores)

        tokenized_corpus = [
            tokenize(self.chunks[position]["text"])
            for position in candidate_positions
        ]
        bm25 = BM25Okapi(tokenized_corpus)
        query_tokens = tokenize(query)
        if query_tokens:
            bm25_scores = np.asarray(
                bm25.get_scores(query_tokens),
                dtype=np.float32,
            )
        else:
            bm25_scores = np.zeros(
                len(candidate_positions),
                dtype=np.float32,
            )
        bm25_normalized = min_max_normalize(bm25_scores)

        hybrid_scores = (
            SEMANTIC_WEIGHT * semantic_normalized
            + BM25_WEIGHT * bm25_normalized
        ).astype(np.float32)

        results = [
            _result_from_chunk(
                self.chunks[position],
                position,
                semantic_score=float(semantic_scores[local_position]),
                semantic_normalized=float(
                    semantic_normalized[local_position]
                ),
                bm25_score=float(bm25_scores[local_position]),
                bm25_normalized=float(bm25_normalized[local_position]),
                hybrid_score=float(hybrid_scores[local_position]),
            )
            for local_position, position in enumerate(candidate_positions)
        ]
        results.sort(
            key=lambda item: (
                item["hybrid_score"],
                item["semantic_score"],
                item["chunk_id"],
            ),
            reverse=True,
        )
        return results[: min(top_k, len(results))]

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        query = validate_search_parameters(query, top_k)

        if self.reranker_model is None:
            raise RuntimeError("Reranker model не завантажено")

        if not candidates:
            raise ValueError("Немає candidates для reranking")

        pairs = [
            (query, candidate["text"])
            for candidate in candidates
        ]
        raw_scores = np.asarray(
            self.reranker_model.predict(
                pairs,
                show_progress_bar=False,
                convert_to_numpy=True,
            ),
            dtype=np.float32,
        ).reshape(-1)

        if raw_scores.shape[0] != len(candidates):
            raise ValueError(
                "Reranker повернув неочікувану кількість scores"
            )

        if not np.isfinite(raw_scores).all():
            raise ValueError("Reranker scores містять NaN або infinity")

        clipped_scores = np.clip(raw_scores, -60.0, 60.0)
        sigmoid_scores = (
            1.0 / (1.0 + np.exp(-clipped_scores))
        ).astype(np.float32)

        results = [
            {
                **candidate,
                "reranker_raw_score": float(raw_scores[position]),
                "reranker_score": float(sigmoid_scores[position]),
            }
            for position, candidate in enumerate(candidates)
        ]
        results.sort(
            key=lambda item: (
                item["reranker_raw_score"],
                item["hybrid_score"],
                item["chunk_id"],
            ),
            reverse=True,
        )
        return results[: min(top_k, len(results))]

    def reranked_search(
        self,
        query: str,
        top_k: int,
        candidate_k: int,
        positions: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        query = validate_search_parameters(
            query,
            top_k,
            candidate_k,
        )
        hybrid_candidates = self.hybrid_search(
            query=query,
            top_k=candidate_k,
            positions=positions,
        )
        return self.rerank(
            query=query,
            candidates=hybrid_candidates,
            top_k=top_k,
        )


def load_reranker_model(model_name: str) -> CrossEncoder:
    if model_name == QWEN_RERANKER_MODEL_NAME:
        return CrossEncoder(
            model_name,
            max_length=512,
            prompts={"retrieval": QWEN_RERANKER_PROMPT},
            default_prompt_name="retrieval",
        )

    return CrossEncoder(model_name, max_length=512)


def load_pipeline(
    load_reranker: bool = True,
    reranker_model_name: str = RERANKER_MODEL_NAME,
) -> tuple[
    RetrievalPipeline,
    dict[str, Any],
    Any,
]:
    chunks = load_chunks(CHUNKS_PATH)
    manifest = load_manifest(MANIFEST_PATH)
    index = load_faiss_index(INDEX_PATH)
    embeddings = load_embeddings(EMBEDDINGS_PATH)

    validate_artifacts(chunks, manifest, index)
    validate_embeddings(embeddings, chunks, manifest)

    embedding_model = SentenceTransformer(manifest["model"])
    reranker_model = (
        load_reranker_model(reranker_model_name)
        if load_reranker
        else None
    )

    pipeline = RetrievalPipeline(
        chunks=chunks,
        embeddings=embeddings,
        embedding_model=embedding_model,
        reranker_model=reranker_model,
    )
    return pipeline, manifest, index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Порівняння semantic baseline, BM25 hybrid і "
            "BGE cross-encoder reranking"
        )
    )
    parser.add_argument(
        "query",
        help="Питання користувача",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Кількість результатів (default: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--candidate-k",
        type=int,
        default=DEFAULT_CANDIDATE_K,
        help=(
            "Кількість hybrid candidates для reranker "
            f"(default: {DEFAULT_CANDIDATE_K})"
        ),
    )
    parser.add_argument(
        "--source-file",
        help=(
            "Metadata filter, наприклад "
            "data/raw/exam_time_planning.html"
        ),
    )
    parser.add_argument(
        "--reranker-model",
        choices=sorted(RERANKER_MODELS),
        default=DEFAULT_RERANKER_KEY,
        help=(
            "Reranker model: bge (швидший) або qwen3-4b "
            f"(default: {DEFAULT_RERANKER_KEY})"
        ),
    )
    return parser.parse_args()


def text_preview(text: str, limit: int = 260) -> str:
    compact_text = " ".join(text.split())
    if len(compact_text) <= limit:
        return compact_text
    return compact_text[: limit - 1].rstrip() + "…"


def print_results(
    title: str,
    results: list[dict[str, Any]],
    score_fields: tuple[tuple[str, str], ...],
) -> None:
    print_section(title)

    for rank, result in enumerate(results, start=1):
        metadata = result["metadata"]
        scores = " | ".join(
            f"{label}={result[field]:.4f}"
            for field, label in score_fields
        )

        print()
        print(f"Top-{rank}: {result['chunk_id']} | {scores}")
        print(f"Document: {result['document_id']}")
        print(f"Source: {result['source_file']}")
        print(f"Section: {metadata.get('section', '—')}")
        print(f"Text: {text_preview(result['text'])}")


def main() -> None:
    args = parse_args()
    validate_search_parameters(
        args.query,
        args.top_k,
        args.candidate_k,
    )

    print_section("ЗАВАНТАЖЕННЯ RETRIEVAL")
    pipeline, manifest, index = load_pipeline(load_reranker=False)
    positions = pipeline.positions_for_source(args.source_file)
    effective_top_k = min(args.top_k, len(positions))
    effective_candidate_k = min(args.candidate_k, len(positions))
    reranker_model_name = RERANKER_MODELS[args.reranker_model]

    print(f"Chunks: {len(pipeline.chunks)}")
    print(f"Embedding model: {manifest['model']}")
    print(f"FAISS vectors: {index.ntotal}")
    print(f"Source filter: {args.source_file or 'none'}")
    print(
        f"Search space: {len(positions)} із "
        f"{len(pipeline.chunks)} chunks"
    )
    print(
        f"Hybrid weights: semantic={SEMANTIC_WEIGHT:.2f}, "
        f"BM25={BM25_WEIGHT:.2f}"
    )
    print(f"Rerank candidates: {effective_candidate_k}")
    print(f"Reranker: {reranker_model_name}")
    print("Перевірка артефактів: OK")

    semantic_results = pipeline.semantic_search(
        query=args.query,
        top_k=effective_top_k,
        positions=positions,
    )
    hybrid_results = pipeline.hybrid_search(
        query=args.query,
        top_k=effective_top_k,
        positions=positions,
    )
    hybrid_candidates = pipeline.hybrid_search(
        query=args.query,
        top_k=effective_candidate_k,
        positions=positions,
    )

    print_section("ЗАВАНТАЖЕННЯ RERANKER")
    print(f"Model: {reranker_model_name}")
    pipeline.reranker_model = load_reranker_model(
        reranker_model_name
    )
    reranked_results = pipeline.rerank(
        query=args.query,
        candidates=hybrid_candidates,
        top_k=effective_top_k,
    )

    print_results(
        "SEMANTIC BASELINE",
        semantic_results,
        (("semantic_score", "semantic"),),
    )
    print_results(
        "BM25 HYBRID",
        hybrid_results,
        (
            ("semantic_score", "semantic"),
            ("bm25_score", "BM25"),
            ("hybrid_score", "hybrid"),
        ),
    )
    print_results(
        f"{args.reranker_model.upper()} RERANKING",
        reranked_results,
        (
            ("hybrid_score", "hybrid"),
            ("reranker_score", "reranker"),
        ),
    )


if __name__ == "__main__":
    main()
