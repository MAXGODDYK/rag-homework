from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.agent_flow import (
    MAX_GOAL_LENGTH,
    detect_language,
    generate_examples,
    mock_get_daily_routine,
    mock_get_exam_plan,
    route_goal,
    run_agent,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("question", "expected_route"),
    [
        (
            "Як скласти план підготовки до іспиту?",
            "exam_preparation",
        ),
        (
            "Як організувати режим дня, сон і перерви?",
            "daily_routine",
        ),
        (
            "Create an exam study plan with sleep and breaks.",
            "combined_planning",
        ),
        ("Розкажи щось корисне.", "clarification"),
    ],
)
def test_route_goal(question: str, expected_route: str) -> None:
    assert route_goal(question) == expected_route


@pytest.mark.parametrize(
    ("question", "expected_language"),
    [
        ("Як підготуватися до іспиту?", "uk"),
        ("Как организовать режим дня?", "ru"),
        ("How should I prepare for an exam?", "en"),
    ],
)
def test_detect_language(question: str, expected_language: str) -> None:
    assert detect_language(question) == expected_language


def test_exam_route_calls_only_exam_tool() -> None:
    state = run_agent("Як підготуватися до іспиту?")

    assert state.selected_route == "exam_preparation"
    assert [call.tool_name for call in state.tool_calls] == [
        "mock_get_exam_plan"
    ]
    assert len(state.observations) == 1
    assert state.current_step == "completed"
    assert not state.needs_clarification


def test_daily_route_calls_only_routine_tool_in_russian() -> None:
    state = run_agent(
        "Как организовать режим дня и отдых между занятиями?"
    )

    assert state.language == "ru"
    assert state.selected_route == "daily_routine"
    assert [call.tool_name for call in state.tool_calls] == [
        "mock_get_daily_routine"
    ]
    assert "сбалансированного" in state.final_answer


def test_combined_route_executes_tools_in_fixed_order() -> None:
    state = run_agent(
        "Create an exam study plan that includes sleep and breaks."
    )

    assert state.selected_route == "combined_planning"
    assert [call.tool_name for call in state.tool_calls] == [
        "mock_get_exam_plan",
        "mock_get_daily_routine",
    ]
    assert [item.sequence for item in state.observations] == [1, 2]
    assert "Seven-day preparation plan" in state.final_answer
    assert "balanced study day" in state.final_answer


def test_state_history_records_every_transition() -> None:
    state = run_agent(
        "Create an exam study plan that includes sleep and breaks."
    )

    assert [snapshot.step for snapshot in state.state_history] == list(
        range(1, len(state.state_history) + 1)
    )
    assert [snapshot.phase for snapshot in state.state_history] == [
        "validation",
        "routing",
        "action",
        "observation",
        "action",
        "observation",
        "finalization",
    ]
    assert state.state_history[-1].current_step == "completed"
    assert state.state_history[-1].tool_call_count == 2
    assert state.state_history[-1].observation_count == 2


def test_clarification_does_not_call_tools() -> None:
    state = run_agent("Розкажи щось корисне.")

    assert state.selected_route == "clarification"
    assert state.needs_clarification
    assert state.tool_calls == []
    assert state.observations == []
    assert [item.phase for item in state.state_history] == [
        "validation",
        "routing",
        "finalization",
    ]


def test_empty_and_too_long_goals_are_rejected() -> None:
    with pytest.raises(ValueError, match="порожнім"):
        run_agent("   ")
    with pytest.raises(ValueError, match=str(MAX_GOAL_LENGTH)):
        run_agent("a" * (MAX_GOAL_LENGTH + 1))


def test_tools_and_workflow_are_deterministic() -> None:
    first = run_agent("Як підготуватися до іспиту?")
    second = run_agent("Як підготуватися до іспиту?")

    assert first == second
    assert mock_get_exam_plan("uk") == mock_get_exam_plan("uk")
    assert mock_get_daily_routine("en") == mock_get_daily_routine("en")


def test_generate_examples_writes_five_real_traces(tmp_path: Path) -> None:
    output_path = tmp_path / "agent_flow_examples.md"

    states = generate_examples(output_path)
    report = output_path.read_text(encoding="utf-8")

    assert len(states) == 5
    assert report.count("**Question:**") == 5
    assert "`combined_planning`" in report
    assert "**State after steps:**" in report


def test_cli_json_returns_machine_readable_state() -> None:
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "HW_6.scripts.agent_flow",
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

    payload = json.loads(process.stdout)
    assert payload["selected_route"] == "exam_preparation"
    assert payload["current_step"] == "completed"
    assert payload["tool_calls"][0]["tool_name"] == "mock_get_exam_plan"
