from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.evaluate_chatbot import (
    EvalRecord,
    REQUIRED_COLUMNS,
    calculate_metrics,
    load_cases,
    write_outputs,
)


def record(
    identifier: int,
    *,
    task_success: str = "yes",
    groundedness: str = "good",
    latency_ms: int = 100,
    errors: str = "none",
) -> EvalRecord:
    return EvalRecord(
        id=identifier,
        question="Question",
        expected_behavior="Expected",
        answer="Answer",
        retrieved_chunks="[]",
        route_or_mode="rag",
        tools_used="",
        task_success=task_success,  # type: ignore[arg-type]
        groundedness=groundedness,  # type: ignore[arg-type]
        answer_quality="good",
        latency_ms=latency_ms,
        errors=errors,
        notes="note",
        evaluation_mode="test",
        retrieval_latency_ms=50,
        generation_latency_ms=50,
        observed_at_utc="2026-01-01T00:00:00+00:00",
    )


def test_eval_set_has_ten_unique_cases_and_required_coverage() -> None:
    cases = load_cases()

    assert len(cases) == 10
    assert len({case.id for case in cases}) == len(cases)
    assert {case.kind for case in cases} == {"rag", "tool", "agent"}
    assert sum(case.expect_fallback for case in cases) == 2
    assert any("складний" in case.expected_behavior for case in cases)


def test_metrics_calculate_success_groundedness_latency_and_errors() -> None:
    records = [
        record(1, latency_ms=100),
        record(2, task_success="partial", groundedness="partial", latency_ms=200, errors="wrong_retrieval"),
        record(3, task_success="no", groundedness="bad", latency_ms=300, errors="unexpected_fallback"),
    ]

    metrics = calculate_metrics(records)

    assert metrics["total_cases"] == 3
    assert metrics["success_rate"] == pytest.approx(1 / 3)
    assert metrics["groundedness_good_rate"] == pytest.approx(1 / 3)
    assert metrics["average_latency_ms"] == 200
    assert metrics["top_error_types"] == {
        "none": 1,
        "wrong_retrieval": 1,
        "unexpected_fallback": 1,
    }


def test_write_outputs_preserves_all_required_columns_and_machine_traces(tmp_path: Path) -> None:
    paths = write_outputs([record(1), record(2, errors="wrong_retrieval")], tmp_path)

    with paths["csv"].open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        assert reader.fieldnames is not None
        assert set(REQUIRED_COLUMNS) <= set(reader.fieldnames)
    assert len(rows) == 2

    trace_lines = paths["traces"].read_text(encoding="utf-8").splitlines()
    assert len(trace_lines) == 2
    assert json.loads(trace_lines[0])["id"] == 1

    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    assert metrics["total_cases"] == 2
    assert "Три головні проблеми" in paths["quality_report"].read_text(encoding="utf-8")
