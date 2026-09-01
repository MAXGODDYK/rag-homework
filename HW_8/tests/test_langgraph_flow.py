from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.langgraph_flow import generate_examples, run_framework_agent


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("question", "expected_route", "expected_nodes"),
    [
        (
            "Як скласти план підготовки до іспиту?",
            "exam_preparation",
            ["validate_request", "classify_request", "run_exam_plan", "build_answer"],
        ),
        (
            "Як організувати режим дня, сон і перерви?",
            "daily_routine",
            ["validate_request", "classify_request", "run_daily_routine", "build_answer"],
        ),
        (
            "Create an exam study plan that includes sleep and breaks.",
            "combined_planning",
            [
                "validate_request",
                "classify_request",
                "run_exam_plan",
                "run_daily_routine",
                "build_answer",
            ],
        ),
        (
            "Розкажи щось корисне.",
            "clarification",
            ["validate_request", "classify_request", "build_answer"],
        ),
    ],
)
def test_conditional_routes_execute_expected_graph_nodes(
    question: str,
    expected_route: str,
    expected_nodes: list[str],
) -> None:
    state = run_framework_agent(question)

    assert state["selected_route"] == expected_route
    assert state["executed_nodes"] == expected_nodes


def test_combined_route_runs_tools_in_the_fixed_order() -> None:
    state = run_framework_agent(
        "Create an exam study plan that includes sleep and breaks."
    )

    assert state["tool_calls"] == [
        "mock_get_exam_plan",
        "mock_get_daily_routine",
    ]
    assert [item["tool_name"] for item in state["observations"]] == state["tool_calls"]
    assert "Seven-day preparation plan" in state["final_answer"]
    assert "balanced study day" in state["final_answer"]


def test_clarification_does_not_call_a_tool() -> None:
    state = run_framework_agent("Розкажи щось корисне.")

    assert state["needs_clarification"] is True
    assert state["tool_calls"] == []
    assert state["observations"] == []


@pytest.mark.parametrize("question", ["   ", "a" * 1001])
def test_invalid_input_is_stopped_before_routing_and_tools(question: str) -> None:
    state = run_framework_agent(question)

    assert state["validation_error"]
    assert state["executed_nodes"] == ["validate_request", "build_answer"]
    assert state["tool_calls"] == []
    assert state["needs_clarification"] is True


def test_three_generated_examples_contain_required_trace_fields(tmp_path: Path) -> None:
    output_path = tmp_path / "langgraph_examples.md"

    states = generate_examples(output_path)
    report = output_path.read_text(encoding="utf-8")

    assert len(states) == 3
    assert report.count("**Input question:**") == 3
    assert report.count("**Selected route:**") == 3
    assert report.count("**Executed nodes:**") == 3
    assert report.count("**Final state:**") == 3
    assert report.count("**Final answer:**") == 3


def test_cli_json_returns_complete_final_state() -> None:
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "HW_8.scripts.langgraph_flow",
            "How should I prepare for an exam?",
            "--json",
        ],
        cwd=PROJECT_ROOT.parent,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    state = json.loads(process.stdout)
    assert state["selected_route"] == "exam_preparation"
    assert state["executed_nodes"][-1] == "build_answer"
    assert state["tool_calls"] == ["mock_get_exam_plan"]
