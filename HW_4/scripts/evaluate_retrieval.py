from __future__ import annotations

import gc
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import numpy as np

from retrieval_improved import (
    BM25_WEIGHT,
    BGE_RERANKER_MODEL_NAME,
    DEFAULT_CANDIDATE_K,
    DEFAULT_TOP_K,
    QWEN_RERANKER_MODEL_NAME,
    SEMANTIC_WEIGHT,
    RetrievalPipeline,
    load_pipeline,
    load_reranker_model,
    text_preview,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_PATH = (
    PROJECT_ROOT / "data" / "evaluation" / "retrieval_eval.jsonl"
)
JSON_OUTPUT_PATH = (
    PROJECT_ROOT / "outputs" / "retrieval_evaluation.json"
)
MARKDOWN_OUTPUT_PATH = (
    PROJECT_ROOT / "outputs" / "retrieval_comparison.md"
)

SYSTEM_LABELS = {
    "semantic": "Semantic baseline",
    "hybrid": "Semantic + BM25",
    "reranked_bge": "Semantic + BM25 + BGE",
    "reranked_qwen": "Semantic + BM25 + Qwen3-4B",
}


def load_evaluation_cases(
    path: Path,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Evaluation dataset не знайдено: {path}")

    required_fields = {
        "query_id",
        "query",
        "relevant_chunk_ids",
        "expected_source_file",
    }
    chunk_ids = {chunk["chunk_id"] for chunk in chunks}
    source_files = {chunk["source_file"] for chunk in chunks}
    seen_query_ids: set[str] = set()
    cases: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                case = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Некоректний JSON у рядку {line_number}: {error}"
                ) from error

            if not isinstance(case, dict):
                raise ValueError(
                    f"Рядок {line_number} повинен містити JSON object"
                )

            missing_fields = required_fields - case.keys()
            if missing_fields:
                raise ValueError(
                    f"Рядок {line_number}: відсутні поля "
                    f"{sorted(missing_fields)}"
                )

            query_id = case["query_id"]
            query = case["query"]
            relevant_ids = case["relevant_chunk_ids"]
            expected_source = case["expected_source_file"]

            if not isinstance(query_id, str) or not query_id.strip():
                raise ValueError(
                    f"Рядок {line_number}: query_id повинен бути непорожнім"
                )
            if query_id in seen_query_ids:
                raise ValueError(f"Query ID не унікальний: {query_id}")
            seen_query_ids.add(query_id)

            if not isinstance(query, str) or not query.strip():
                raise ValueError(
                    f"Рядок {line_number}: query повинен бути непорожнім"
                )

            if not isinstance(relevant_ids, list) or not relevant_ids:
                raise ValueError(
                    f"Рядок {line_number}: relevant_chunk_ids "
                    "повинен бути непорожнім list"
                )
            if len(relevant_ids) != len(set(relevant_ids)):
                raise ValueError(
                    f"Рядок {line_number}: relevant_chunk_ids "
                    "містить дублікати"
                )

            unknown_ids = set(relevant_ids) - chunk_ids
            if unknown_ids:
                raise ValueError(
                    f"Рядок {line_number}: невідомі chunk IDs "
                    f"{sorted(unknown_ids)}"
                )

            if expected_source not in source_files:
                raise ValueError(
                    f"Рядок {line_number}: невідомий source_file "
                    f"{expected_source}"
                )

            cases.append(case)

    if not cases:
        raise ValueError("Evaluation dataset не містить queries")

    return cases


def ranking_metrics(
    results: list[dict[str, Any]],
    relevant_chunk_ids: list[str],
    top_k: int,
) -> dict[str, float]:
    relevant = set(relevant_chunk_ids)
    retrieved_ids = [
        result["chunk_id"]
        for result in results[:top_k]
    ]
    relevant_retrieved = [
        chunk_id
        for chunk_id in retrieved_ids
        if chunk_id in relevant
    ]
    first_relevant_rank = next(
        (
            rank
            for rank, chunk_id in enumerate(retrieved_ids, start=1)
            if chunk_id in relevant
        ),
        None,
    )

    return {
        "hit_rate_at_1": float(
            bool(retrieved_ids and retrieved_ids[0] in relevant)
        ),
        "hit_rate_at_3": float(bool(relevant_retrieved)),
        "recall_at_3": len(relevant_retrieved) / len(relevant),
        "mrr_at_3": (
            1.0 / first_relevant_rank
            if first_relevant_rank is not None
            else 0.0
        ),
        "first_relevant_rank": (
            float(first_relevant_rank)
            if first_relevant_rank is not None
            else 0.0
        ),
    }


def serializable_result(result: dict[str, Any]) -> dict[str, Any]:
    output = {
        "chunk_id": result["chunk_id"],
        "document_id": result["document_id"],
        "source_file": result["source_file"],
        "section": result["metadata"].get("section", ""),
        "preview": text_preview(result["text"], limit=180),
    }
    score_fields = (
        "semantic_score",
        "semantic_normalized",
        "bm25_score",
        "bm25_normalized",
        "hybrid_score",
        "reranker_raw_score",
        "reranker_score",
    )

    for field in score_fields:
        if field in result:
            output[field] = float(result[field])

    return output


def first_relevant_rank(
    system_result: dict[str, Any],
) -> int | None:
    value = int(system_result["metrics"]["first_relevant_rank"])
    return value if value > 0 else None


def aggregate_system_metrics(
    query_results: list[dict[str, Any]],
    system_name: str,
) -> dict[str, float]:
    metric_names = (
        "hit_rate_at_1",
        "hit_rate_at_3",
        "recall_at_3",
        "mrr_at_3",
    )
    latencies = np.asarray(
        [
            query_result["systems"][system_name]["latency_ms"]
            for query_result in query_results
        ],
        dtype=np.float64,
    )
    output = {
        metric_name: float(
            np.mean(
                [
                    query_result["systems"][system_name]["metrics"][
                        metric_name
                    ]
                    for query_result in query_results
                ]
            )
        )
        for metric_name in metric_names
    }
    output["mean_latency_ms"] = float(np.mean(latencies))
    output["p95_latency_ms"] = float(np.percentile(latencies, 95))
    return output


def compare_first_relevant_ranks(
    query_results: list[dict[str, Any]],
    target_system: str,
) -> dict[str, list[str]]:
    comparison = {
        "improved": [],
        "unchanged": [],
        "worsened": [],
    }

    for query_result in query_results:
        baseline_rank = first_relevant_rank(
            query_result["systems"]["semantic"]
        )
        target_rank = first_relevant_rank(
            query_result["systems"][target_system]
        )
        baseline_value = baseline_rank or DEFAULT_TOP_K + 1
        target_value = target_rank or DEFAULT_TOP_K + 1

        if target_value < baseline_value:
            comparison["improved"].append(query_result["query_id"])
        elif target_value > baseline_value:
            comparison["worsened"].append(query_result["query_id"])
        else:
            comparison["unchanged"].append(query_result["query_id"])

    return comparison


def primary_score(
    system_name: str,
    result: dict[str, Any],
) -> float:
    if system_name == "semantic":
        return result["semantic_score"]
    if system_name == "hybrid":
        return result["hybrid_score"]
    return result["reranker_score"]


def format_query_ids(query_ids: list[str]) -> str:
    return ", ".join(f"`{query_id}`" for query_id in query_ids) or "немає"


def build_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Evaluation semantic, BM25, BGE та Qwen3-4B reranking",
        "",
        "## Конфігурація",
        "",
        (
            f"- Embedding model: `{payload['config']['embedding_model']}`"
        ),
        (
            "- BGE reranker: "
            f"`{payload['config']['reranker_models']['bge']}`"
        ),
        (
            "- Qwen reranker: "
            f"`{payload['config']['reranker_models']['qwen3_4b']}`"
        ),
        (
            "- Hybrid formula: "
            f"`{SEMANTIC_WEIGHT:.2f} × semantic_normalized + "
            f"{BM25_WEIGHT:.2f} × bm25_normalized`"
        ),
        (
            f"- Corpus: {payload['config']['chunk_count']} chunks; "
            f"queries: {payload['config']['query_count']}; "
            f"top-k: {payload['config']['top_k']}; "
            f"candidate-k: {payload['config']['candidate_k']}"
        ),
        "",
        "Розмітка релевантності створена вручну до запуску evaluation. "
        "Основні метрики всіх чотирьох систем рахуються без metadata filter "
        "на однаковому corpus із 25 chunks. Час завантаження моделей не "
        "входить у latency; перед вимірюванням виконано warm-up.",
        "",
        "## Зведені метрики",
        "",
        (
            "| System | HitRate@1 | HitRate@3 | Recall@3 | MRR@3 | "
            "Mean latency, ms | P95 latency, ms |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for system_name in SYSTEM_LABELS:
        metrics = payload["metrics"][system_name]
        lines.append(
            f"| {SYSTEM_LABELS[system_name]} "
            f"| {metrics['hit_rate_at_1']:.3f} "
            f"| {metrics['hit_rate_at_3']:.3f} "
            f"| {metrics['recall_at_3']:.3f} "
            f"| {metrics['mrr_at_3']:.3f} "
            f"| {metrics['mean_latency_ms']:.1f} "
            f"| {metrics['p95_latency_ms']:.1f} |"
        )

    lines.extend(
        [
            "",
            "## Metadata filtering",
            "",
            (
                "| Query | Expected source | Candidates | "
                "Усі top-3 відповідають filter |"
            ),
            "|---|---|---:|---|",
        ]
    )

    for check in payload["metadata_filter_checks"]:
        lines.append(
            f"| `{check['query_id']}` "
            f"| `{check['source_file']}` "
            f"| {check['candidate_count']} "
            f"| {'так' if check['all_results_match'] else 'ні'} |"
        )

    lines.extend(
        [
            "",
            "## Перший релевантний результат",
            "",
            "| Query | Semantic | Hybrid | BGE | Qwen3-4B |",
            "|---|---:|---:|---:|---:|",
        ]
    )

    for query_result in payload["queries"]:
        rank_values = []
        for system_name in SYSTEM_LABELS:
            rank = first_relevant_rank(
                query_result["systems"][system_name]
            )
            rank_values.append(str(rank) if rank is not None else "—")
        lines.append(
            f"| `{query_result['query_id']}` "
            f"| {rank_values[0]} | {rank_values[1]} "
            f"| {rank_values[2]} | {rank_values[3]} |"
        )

    lines.extend(["", "## Детальні top-3", ""])

    for query_result in payload["queries"]:
        relevant_ids = set(query_result["relevant_chunk_ids"])
        lines.extend(
            [
                (
                    f"### {query_result['query_id']}: "
                    f"{query_result['query']}"
                ),
                "",
                (
                    "Relevant: "
                    + ", ".join(
                        f"`{chunk_id}`"
                        for chunk_id in query_result[
                            "relevant_chunk_ids"
                        ]
                    )
                ),
                "",
                "| System | Rank | Chunk | Score | Relevant | Source |",
                "|---|---:|---|---:|---|---|",
            ]
        )

        for system_name in SYSTEM_LABELS:
            results = query_result["systems"][system_name]["results"]
            for rank, result in enumerate(results, start=1):
                is_relevant = result["chunk_id"] in relevant_ids
                lines.append(
                    f"| {SYSTEM_LABELS[system_name]} "
                    f"| {rank} "
                    f"| `{result['chunk_id']}` "
                    f"| {primary_score(system_name, result):.4f} "
                    f"| {'так' if is_relevant else 'ні'} "
                    f"| `{result['source_file']}` |"
                )
        lines.append("")

    baseline = payload["metrics"]["semantic"]
    lines.extend(["## Аналіз результатів", ""])

    for system_name in ("reranked_bge", "reranked_qwen"):
        comparison = payload["rank_comparison"][system_name]
        reranked = payload["metrics"][system_name]
        hit_delta = (
            reranked["hit_rate_at_1"] - baseline["hit_rate_at_1"]
        )
        mrr_delta = reranked["mrr_at_3"] - baseline["mrr_at_3"]
        lines.extend(
            [
                (
                    f"- {SYSTEM_LABELS[system_name]}: перший релевантний "
                    f"chunk покращено для {len(comparison['improved'])} "
                    f"queries ({format_query_ids(comparison['improved'])}), "
                    f"без змін для {len(comparison['unchanged'])} "
                    f"({format_query_ids(comparison['unchanged'])}), "
                    f"погіршено для {len(comparison['worsened'])} "
                    f"({format_query_ids(comparison['worsened'])})."
                ),
                (
                    "  Зміна відносно semantic baseline: "
                    f"`HitRate@1 {hit_delta:+.3f}`, "
                    f"`MRR@3 {mrr_delta:+.3f}`."
                ),
            ]
        )

    qwen_metrics = payload["metrics"]["reranked_qwen"]
    bge_metrics = payload["metrics"]["reranked_bge"]
    lines.append(
        "- Qwen3-4B порівняно з BGE: "
        f"`HitRate@1 "
        f"{qwen_metrics['hit_rate_at_1'] - bge_metrics['hit_rate_at_1']:+.3f}`, "
        f"`MRR@3 {qwen_metrics['mrr_at_3'] - bge_metrics['mrr_at_3']:+.3f}`, "
        f"`mean latency "
        f"{qwen_metrics['mean_latency_ms'] - bge_metrics['mean_latency_ms']:+.1f} ms`."
    )

    lines.extend(
        [
            "",
            "## Обмеження",
            "",
            "- Evaluation містить лише 8 вручну розмічених queries, тому "
            "метрики мають високу дисперсію.",
            "- BM25 не виконує stemming українських словоформ.",
            "- Min-max scores нормалізуються окремо для кожного query і "
            "не порівнюються між різними queries.",
            "- BGE і особливо Qwen3-4B значно повільніші та потребують "
            "більше пам'яті, ніж semantic і BM25 stages.",
            "- Metadata source передається явно; автоматичний routing "
            "джерела не реалізований.",
            "",
        ]
    )

    return "\n".join(lines)


def evaluate_system(
    query_results: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    system_name: str,
    search_function: Callable[[str], list[dict[str, Any]]],
) -> None:
    print(
        f"=============== {SYSTEM_LABELS[system_name].upper()} ==============="
    )
    search_function(cases[0]["query"])
    print("Warm-up: OK")

    for case, query_result in zip(cases, query_results, strict=True):
        started_at = perf_counter()
        results = search_function(case["query"])
        latency_ms = (perf_counter() - started_at) * 1000.0
        metrics = ranking_metrics(
            results,
            case["relevant_chunk_ids"],
            top_k=DEFAULT_TOP_K,
        )
        query_result["systems"][system_name] = {
            "latency_ms": latency_ms,
            "metrics": metrics,
            "results": [
                serializable_result(result)
                for result in results
            ],
        }
        print(f"{case['query_id']}: OK")


def evaluate() -> dict[str, Any]:
    print("=============== ЗАВАНТАЖЕННЯ PIPELINE ===============")
    pipeline, manifest, index = load_pipeline(load_reranker=False)
    cases = load_evaluation_cases(
        EVALUATION_PATH,
        pipeline.chunks,
    )
    all_positions = list(range(len(pipeline.chunks)))
    query_results = [
        {
            "query_id": case["query_id"],
            "query": case["query"],
            "relevant_chunk_ids": case["relevant_chunk_ids"],
            "expected_source_file": case["expected_source_file"],
            "systems": {},
        }
        for case in cases
    ]

    print(f"Chunks: {len(pipeline.chunks)}")
    print(f"Queries: {len(cases)}")
    print(f"Embedding model: {manifest['model']}")
    print(f"BGE reranker: {BGE_RERANKER_MODEL_NAME}")
    print(f"Qwen reranker: {QWEN_RERANKER_MODEL_NAME}")
    print(f"FAISS vectors: {index.ntotal}")

    evaluate_system(
        query_results,
        cases,
        "semantic",
        lambda query: pipeline.semantic_search(
            query,
            top_k=DEFAULT_TOP_K,
            positions=all_positions,
        ),
    )
    evaluate_system(
        query_results,
        cases,
        "hybrid",
        lambda query: pipeline.hybrid_search(
            query,
            top_k=DEFAULT_TOP_K,
            positions=all_positions,
        ),
    )

    for system_name, model_name in (
        ("reranked_bge", BGE_RERANKER_MODEL_NAME),
        ("reranked_qwen", QWEN_RERANKER_MODEL_NAME),
    ):
        print(
            f"=============== ЗАВАНТАЖЕННЯ {model_name} ==============="
        )
        reranker_model = load_reranker_model(model_name)
        pipeline.reranker_model = reranker_model
        evaluate_system(
            query_results,
            cases,
            system_name,
            lambda query: pipeline.reranked_search(
                query,
                top_k=DEFAULT_TOP_K,
                candidate_k=DEFAULT_CANDIDATE_K,
                positions=all_positions,
            ),
        )
        pipeline.reranker_model = None
        del reranker_model
        gc.collect()

    print("=============== METADATA FILTERING ===============")
    metadata_filter_checks = []
    for case in cases:
        positions = pipeline.positions_for_source(
            case["expected_source_file"]
        )
        filtered_results = pipeline.hybrid_search(
            case["query"],
            top_k=DEFAULT_TOP_K,
            positions=positions,
        )
        all_results_match = all(
            result["source_file"] == case["expected_source_file"]
            for result in filtered_results
        )
        if not all_results_match:
            raise ValueError(
                f"Metadata filtering failed for {case['query_id']}"
            )
        metadata_filter_checks.append(
            {
                "query_id": case["query_id"],
                "source_file": case["expected_source_file"],
                "candidate_count": len(positions),
                "all_results_match": all_results_match,
            }
        )
        print(
            f"{case['query_id']}: {len(positions)} candidates, OK"
        )

    metrics = {
        system_name: aggregate_system_metrics(
            query_results,
            system_name,
        )
        for system_name in SYSTEM_LABELS
    }
    payload = {
        "config": {
            "embedding_model": manifest["model"],
            "reranker_models": {
                "bge": BGE_RERANKER_MODEL_NAME,
                "qwen3_4b": QWEN_RERANKER_MODEL_NAME,
            },
            "chunk_count": len(pipeline.chunks),
            "query_count": len(cases),
            "top_k": DEFAULT_TOP_K,
            "candidate_k": DEFAULT_CANDIDATE_K,
            "semantic_weight": SEMANTIC_WEIGHT,
            "bm25_weight": BM25_WEIGHT,
            "latency_excludes_model_loading": True,
        },
        "metrics": metrics,
        "rank_comparison": {
            system_name: compare_first_relevant_ranks(
                query_results,
                system_name,
            )
            for system_name in (
                "reranked_bge",
                "reranked_qwen",
            )
        },
        "metadata_filter_checks": metadata_filter_checks,
        "queries": query_results,
    }

    for system_name, system_metrics in metrics.items():
        for metric_name in (
            "hit_rate_at_1",
            "hit_rate_at_3",
            "recall_at_3",
            "mrr_at_3",
        ):
            value = system_metrics[metric_name]
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{system_name}.{metric_name} поза межами 0..1"
                )
        if (
            system_metrics["hit_rate_at_3"]
            < system_metrics["hit_rate_at_1"]
        ):
            raise ValueError(
                f"{system_name}: HitRate@3 менше HitRate@1"
            )

    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MARKDOWN_OUTPUT_PATH.write_text(
        build_markdown_report(payload),
        encoding="utf-8",
    )

    print("=============== ЗБЕРЕЖЕННЯ РЕЗУЛЬТАТІВ ===============")
    print(f"JSON: {JSON_OUTPUT_PATH}")
    print(f"Markdown: {MARKDOWN_OUTPUT_PATH}")
    return payload


def main() -> None:
    payload = evaluate()

    print("=============== ПІДСУМОК ===============")
    for system_name, metrics in payload["metrics"].items():
        print(
            f"{SYSTEM_LABELS[system_name]}: "
            f"Hit@1={metrics['hit_rate_at_1']:.3f}, "
            f"Hit@3={metrics['hit_rate_at_3']:.3f}, "
            f"Recall@3={metrics['recall_at_3']:.3f}, "
            f"MRR@3={metrics['mrr_at_3']:.3f}, "
            f"mean={metrics['mean_latency_ms']:.1f} ms"
        )


if __name__ == "__main__":
    main()
