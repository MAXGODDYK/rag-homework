from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_rag import write_markdown


REVIEWS = {
    "q01": (
        "relevant",
        "Відповідь спирається на chunks про конкретну мету, learning "
        "track і зворотний зв’язок; усі наведені поради є в top-3.",
    ),
    "q02": (
        "relevant",
        "Наведені часові межі та застереження про індивідуальну "
        "продуктивність прямо підтримані retrieved chunks.",
    ),
    "q03": (
        "partially relevant",
        "Основний порядок пріоритетів правильний, але формулювання про "
        "важливі нетермінові справи детальніше за фактичний контекст.",
    ),
    "q04": (
        "relevant",
        "Retriever не підняв chunk про «з’їсти жабу», але знайдені "
        "chunks дають іншу grounded пораду: вимірювати відволікання "
        "та змінювати підхід.",
    ),
    "q05": (
        "relevant",
        "Англійська відповідь точно використовує надані тривалості "
        "сесій, перерви та роль сну без зовнішніх чисел.",
    ),
    "q06": (
        "partially relevant",
        "Головний висновок про перерви і продуктивність підтриманий, "
        "але друге речення сформульоване невдало.",
    ),
    "q07": (
        "relevant",
        "Confidence gate відхилив стороннє питання до виклику LLM; "
        "fallback і порожні citations коректні.",
    ),
    "q08": (
        "relevant",
        "Слабкий retrieval відхилено до генерації; система не дає "
        "необґрунтовану персональну пораду.",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "rag_evaluation.json",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=(
            PROJECT_ROOT / "outputs" / "rag_answers_examples.md"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report: dict[str, Any] = json.loads(
        args.json.read_text(encoding="utf-8")
    )
    reviewed_ids: set[str] = set()
    for item in report["results"]:
        if item["status"] != "ok":
            continue
        if item["requested_provider"] != "local":
            continue
        question_id = item["question_id"]
        relevance, comment = REVIEWS[question_id]
        item["manual_relevance"] = relevance
        item["manual_comment"] = comment
        reviewed_ids.add(question_id)

    if reviewed_ids != set(REVIEWS):
        raise ValueError(
            "Evaluation results do not match the eight review cases"
        )

    report["summary"]["manual_reviews"] = {
        label: sum(
            item.get("manual_relevance") == label
            for item in report["results"]
        )
        for label in ("relevant", "partially relevant", "not relevant")
    }
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, args.markdown)
    print("Manual HW4 reviews applied: 8")


if __name__ == "__main__":
    main()
