from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import load_settings
from scripts.rag.service import RagAnswerService


QUESTIONS = [
    {
        "question_id": "q01",
        "question": "Як скласти реалістичний план підготовки до іспиту?",
        "expect_fallback": False,
        "comment": (
            "Перевіряється grounded план із конкретною метою та "
            "послідовними навчальними кроками."
        ),
    },
    {
        "question_id": "q02",
        "question": (
            "Коли протягом дня мозок найкраще засвоює "
            "навчальний матеріал?"
        ),
        "expect_fallback": False,
        "comment": (
            "Перевіряється відповідь про усереднені часові межі "
            "та індивідуальний час продуктивності."
        ),
    },
    {
        "question_id": "q03",
        "question": "Як визначити, які справи термінові, а які важливі?",
        "expect_fallback": False,
        "comment": (
            "Перевіряється використання chunks про пріоритети "
            "і невідкладні справи."
        ),
    },
    {
        "question_id": "q04",
        "question": "Що робити, коли постійно відкладаю навчання?",
        "expect_fallback": False,
        "comment": (
            "Очікується порада, прямо підтримана методом "
            "«з’їсти жабу»."
        ),
    },
    {
        "question_id": "q05",
        "question": (
            "How can a student balance studying, sleep, and rest "
            "without burnout?"
        ),
        "expect_fallback": False,
        "comment": (
            "Перевіряється англомовна grounded відповідь за "
            "україномовним контекстом."
        ),
    },
    {
        "question_id": "q06",
        "question": "Чи потрібні перерви під час тривалого навчання?",
        "expect_fallback": False,
        "comment": (
            "Очікуються конкретні рекомендації про перерви "
            "між навчальними сесіями."
        ),
    },
    {
        "question_id": "q07",
        "question": "Яка столиця Франції?",
        "expect_fallback": True,
        "comment": (
            "Явно стороннє питання повинно бути відхилене "
            "confidence gate без виклику LLM."
        ),
    },
    {
        "question_id": "q08",
        "question": "Чи потрібно мені змінити університет?",
        "expect_fallback": True,
        "comment": (
            "Слабкий retrieval не містить підстав для персональної "
            "поради, тому очікується fallback."
        ),
    },
]


def preview(text: str, limit: int = 240) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# HW4: приклади grounded RAG",
        "",
        "Конфігурація: semantic + BM25 (0.75/0.25), "
        "candidate-k=10, BGE reranking, top-k=3, "
        "raw BGE confidence gate=0.005.",
        "",
    ]
    availability = report["provider_availability"]
    for provider, status in availability.items():
        state = "доступний" if status["available"] else "недоступний"
        lines.append(
            f"- `{provider}`: {state} — {status['reason']}"
        )
    lines.append("")
    lines.append(
        "OpenAI-результати не вигадуються: якщо ключ не налаштовано, "
        "вони позначаються як `skipped`."
    )

    for item in report["results"]:
        lines.extend(
            [
                "",
                f"## {item['question_id']}: {item['question']}",
                "",
                f"- Requested provider: `{item['requested_provider']}`",
                f"- Status: `{item['status']}`",
            ]
        )
        if item["status"] != "ok":
            lines.append(f"- Причина: {item['error']}")
            continue

        lines.extend(
            [
                f"- Actual provider: `{item['provider']}`",
                f"- Fallback: `{str(item['is_fallback']).lower()}`",
                f"- Latency: `{item['latency_ms']:.0f} ms`",
                f"- Citations: "
                + (
                    ", ".join(
                        f"`{citation}`"
                        for citation in item["citations"]
                    )
                    if item["citations"]
                    else "немає"
                ),
                "",
                f"**Відповідь:** {item['answer']}",
                "",
                "**Retrieved chunks:**",
                "",
            ]
        )
        for rank, chunk in enumerate(
            item["retrieved_chunks"],
            start=1,
        ):
            lines.append(
                f"{rank}. `{chunk['chunk_id']}` — "
                f"raw BGE `{chunk['reranker_raw_score']:.4f}`; "
                f"`{chunk['source_file']}`; {preview(chunk['text'])}"
            )
        lines.extend(
            [
                "",
                f"**Ручна оцінка:** "
                f"`{item.get('manual_relevance', 'not reviewed')}`.",
                "",
                f"**Ручний коментар:** {item['manual_comment']} "
                f"Очікування fallback: "
                f"`{str(item['expect_fallback']).lower()}`; "
                f"фактичний результат: "
                f"`{str(item['is_fallback']).lower()}`.",
            ]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate HW4 grounded RAG on eight fixed questions"
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=("openai", "local"),
        default=("openai", "local"),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "rag_evaluation.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=(
            PROJECT_ROOT / "outputs" / "rag_answers_examples.md"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    service = RagAnswerService(settings=settings)
    provider_status = service.provider_status()
    results: list[dict[str, Any]] = []

    for provider_name in args.providers:
        available = provider_status[provider_name]["available"]
        reason = provider_status[provider_name]["reason"]
        for case in QUESTIONS:
            print(
                f"[{provider_name}] {case['question_id']}: "
                f"{case['question']}"
            )
            if not available:
                results.append(
                    {
                        **case,
                        "requested_provider": provider_name,
                        "status": "skipped",
                        "error": reason,
                    }
                )
                continue

            try:
                answer = service.answer(
                    case["question"],
                    provider_name=provider_name,
                    top_k=3,
                    candidate_k=10,
                )
            except Exception as error:
                results.append(
                    {
                        **case,
                        "requested_provider": provider_name,
                        "status": "error",
                        "error": (
                            f"{type(error).__name__}: {error}"
                        ),
                    }
                )
                continue

            results.append(
                {
                    **case,
                    "requested_provider": provider_name,
                    "status": "ok",
                    "error": None,
                    **answer.as_dict(),
                    "manual_relevance": "not reviewed",
                    "manual_comment": case["comment"],
                }
            )

    successful = [
        item for item in results if item["status"] == "ok"
    ]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "top_k": 3,
            "candidate_k": 10,
            "semantic_weight": 0.75,
            "bm25_weight": 0.25,
            "reranker": "BAAI/bge-reranker-v2-m3",
            "confidence_gate_raw_score": (
                settings.minimum_reranker_raw_score
            ),
        },
        "provider_availability": provider_status,
        "results": results,
        "summary": {
            "requested_runs": len(results),
            "successful_runs": len(successful),
            "fallback_matches": sum(
                item["is_fallback"] == item["expect_fallback"]
                for item in successful
            ),
            "invalid_external_citations": sum(
                not set(item["citations"]).issubset(
                    {
                        chunk["chunk_id"]
                        for chunk in item["retrieved_chunks"]
                    }
                )
                for item in successful
            ),
        },
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, args.markdown_output)
    print(
        "Summary: "
        + json.dumps(report["summary"], ensure_ascii=False)
    )
    print(f"JSON: {args.json_output.resolve()}")
    print(f"Markdown: {args.markdown_output.resolve()}")


if __name__ == "__main__":
    main()
