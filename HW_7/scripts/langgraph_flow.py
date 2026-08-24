from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

try:
    from .agent_flow import (
        Language,
        Route,
        detect_language,
        mock_get_daily_routine,
        mock_get_exam_plan,
        route_goal,
        validate_goal,
    )
except ImportError:  # Supports `python scripts/langgraph_flow.py` as well.
    from agent_flow import (
        Language,
        Route,
        detect_language,
        mock_get_daily_routine,
        mock_get_exam_plan,
        route_goal,
        validate_goal,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FrameworkAgentState(TypedDict):
    """State passed between LangGraph nodes.

    The list fields are deliberately replaced by every node instead of using
    reducers. The graph is sequential, therefore each snapshot stays easy to
    inspect and deterministic for the same question.
    """

    user_question: str
    language: Language
    selected_route: Route
    tool_result: dict[str, dict[str, Any]]
    tool_calls: list[str]
    observations: list[dict[str, Any]]
    executed_nodes: list[str]
    needs_clarification: bool
    validation_error: str
    final_answer: str


def _with_node(state: FrameworkAgentState, node_name: str) -> list[str]:
    return [*state["executed_nodes"], node_name]


def validate_request(state: FrameworkAgentState) -> dict[str, Any]:
    """Validate and normalize input before any route or tool is selected."""
    try:
        question = validate_goal(state["user_question"])
    except ValueError as error:
        return {
            "validation_error": str(error),
            "executed_nodes": _with_node(state, "validate_request"),
        }

    return {
        "user_question": question,
        "language": detect_language(question),
        "executed_nodes": _with_node(state, "validate_request"),
    }


def validation_decision(state: FrameworkAgentState) -> Literal[
    "classify_request", "build_answer"
]:
    """Prevent invalid input from reaching classification or mock tools."""
    return "build_answer" if state["validation_error"] else "classify_request"


def classify_request(state: FrameworkAgentState) -> dict[str, Any]:
    """Choose the same deterministic route as the custom HW6 workflow."""
    return {
        "selected_route": route_goal(state["user_question"]),
        "executed_nodes": _with_node(state, "classify_request"),
    }


def route_decision(state: FrameworkAgentState) -> Route:
    """LangGraph conditional edge after request classification."""
    return state["selected_route"]


def run_exam_plan(state: FrameworkAgentState) -> dict[str, Any]:
    result = mock_get_exam_plan(state["language"])
    observation = {
        "tool_name": "mock_get_exam_plan",
        "result": result,
    }
    return {
        "tool_result": {**state["tool_result"], "exam_plan": result},
        "tool_calls": [*state["tool_calls"], "mock_get_exam_plan"],
        "observations": [*state["observations"], observation],
        "executed_nodes": _with_node(state, "run_exam_plan"),
    }


def after_exam_plan(state: FrameworkAgentState) -> Literal[
    "run_daily_routine", "build_answer"
]:
    """A second explicit branch implements the multi-step combined route."""
    if state["selected_route"] == "combined_planning":
        return "run_daily_routine"
    return "build_answer"


def run_daily_routine(state: FrameworkAgentState) -> dict[str, Any]:
    result = mock_get_daily_routine(state["language"])
    observation = {
        "tool_name": "mock_get_daily_routine",
        "result": result,
    }
    return {
        "tool_result": {**state["tool_result"], "daily_routine": result},
        "tool_calls": [*state["tool_calls"], "mock_get_daily_routine"],
        "observations": [*state["observations"], observation],
        "executed_nodes": _with_node(state, "run_daily_routine"),
    }


def _format_exam_plan(result: dict[str, Any], language: Language) -> str:
    headings = {
        "uk": "План підготовки на 7 днів:",
        "ru": "План подготовки на 7 дней:",
        "en": "Seven-day preparation plan:",
    }
    return "\n".join([headings[language], *[f"- {item}" for item in result["plan"]]])


def _format_daily_routine(result: dict[str, Any], language: Language) -> str:
    headings = {
        "uk": "Приклад збалансованого навчального дня:",
        "ru": "Пример сбалансированного учебного дня:",
        "en": "Example of a balanced study day:",
    }
    return "\n".join(
        [headings[language], *[
            f"- {item['time']}: {item['activity']}"
            for item in result["schedule"]
        ]]
    )


def _clarification_answer(language: Language) -> str:
    messages = {
        "uk": (
            "Уточніть, будь ласка: вам потрібен план підготовки до іспиту, "
            "розпорядок навчального дня чи обидва варіанти?"
        ),
        "ru": (
            "Уточните, пожалуйста: вам нужен план подготовки к экзамену, "
            "распорядок учебного дня или оба варианта?"
        ),
        "en": "Please clarify whether you need an exam plan, a daily routine, or both.",
    }
    return messages[language]


def build_answer(state: FrameworkAgentState) -> dict[str, Any]:
    """Finish every branch with a deterministic, inspectable answer."""
    if state["validation_error"]:
        answer = f"Validation error: {state['validation_error']}"
        needs_clarification = True
    elif state["selected_route"] == "clarification":
        answer = _clarification_answer(state["language"])
        needs_clarification = True
    else:
        answer_parts: list[str] = []
        if "exam_plan" in state["tool_result"]:
            answer_parts.append(
                _format_exam_plan(state["tool_result"]["exam_plan"], state["language"])
            )
        if "daily_routine" in state["tool_result"]:
            answer_parts.append(
                _format_daily_routine(
                    state["tool_result"]["daily_routine"], state["language"]
                )
            )
        answer = "\n\n".join(answer_parts)
        needs_clarification = False

    return {
        "final_answer": answer,
        "needs_clarification": needs_clarification,
        "executed_nodes": _with_node(state, "build_answer"),
    }


def build_workflow():
    """Create the compiled LangGraph workflow with explicit conditional edges."""
    workflow = StateGraph(FrameworkAgentState)
    workflow.add_node("validate_request", validate_request)
    workflow.add_node("classify_request", classify_request)
    workflow.add_node("run_exam_plan", run_exam_plan)
    workflow.add_node("run_daily_routine", run_daily_routine)
    workflow.add_node("build_answer", build_answer)

    workflow.add_edge(START, "validate_request")
    workflow.add_conditional_edges(
        "validate_request",
        validation_decision,
        {
            "classify_request": "classify_request",
            "build_answer": "build_answer",
        },
    )
    workflow.add_conditional_edges(
        "classify_request",
        route_decision,
        {
            "exam_preparation": "run_exam_plan",
            "daily_routine": "run_daily_routine",
            "combined_planning": "run_exam_plan",
            "clarification": "build_answer",
        },
    )
    workflow.add_conditional_edges(
        "run_exam_plan",
        after_exam_plan,
        {
            "run_daily_routine": "run_daily_routine",
            "build_answer": "build_answer",
        },
    )
    workflow.add_edge("run_daily_routine", "build_answer")
    workflow.add_edge("build_answer", END)
    return workflow.compile()


app = build_workflow()


def run_framework_agent(user_question: str) -> FrameworkAgentState:
    """Run the graph and return the complete final state."""
    initial_state: FrameworkAgentState = {
        "user_question": user_question,
        "language": "uk",
        "selected_route": "clarification",
        "tool_result": {},
        "tool_calls": [],
        "observations": [],
        "executed_nodes": [],
        "needs_clarification": False,
        "validation_error": "",
        "final_answer": "",
    }
    return app.invoke(initial_state)


EXAMPLE_QUESTIONS = (
    "Як скласти план підготовки до іспиту?",
    "Як організувати режим дня, сон і перерви?",
    "Create an exam study plan that includes sleep and breaks.",
)


def render_example_report(states: list[FrameworkAgentState]) -> str:
    lines = [
        "# HW7 — LangGraph workflow examples",
        "",
        "Усі приклади згенеровано локально через LangGraph без LLM та API.",
        "",
    ]
    for number, state in enumerate(states, start=1):
        lines.extend(
            [
                f"## {number}. {state['selected_route']}",
                "",
                f"**Input question:** {state['user_question']}",
                "",
                f"**Selected route:** `{state['selected_route']}`",
                "",
                "**Executed nodes:** " + " → ".join(
                    f"`{node}`" for node in state["executed_nodes"]
                ),
                "",
                "**Final state:**",
                "",
                "```json",
                json.dumps(state, ensure_ascii=False, indent=2),
                "```",
                "",
                "**Final answer:**",
                "",
                state["final_answer"],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def generate_examples(output_path: Path) -> list[FrameworkAgentState]:
    states = [run_framework_agent(question) for question in EXAMPLE_QUESTIONS]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_example_report(states), encoding="utf-8")
    return states


def print_text_result(state: FrameworkAgentState) -> None:
    print("=============== LANGGRAPH WORKFLOW ===============")
    print(f"Question: {state['user_question']}")
    print(f"Language: {state['language']}")
    print(f"Route: {state['selected_route']}")
    print("\n=============== EXECUTED NODES ===============")
    print(" → ".join(state["executed_nodes"]))
    print("\n=============== FINAL STATE ===============")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    print("\n=============== FINAL ANSWER ===============")
    print(state["final_answer"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LangGraph implementation of the HW6 student-planning workflow",
    )
    parser.add_argument("question", nargs="?")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--generate-examples", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "langgraph_examples.md",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.generate_examples:
        states = generate_examples(args.output)
        print(f"Report: {args.output.resolve()}")
        print(f"Examples: {len(states)}")
        return 0
    if args.question is None:
        raise SystemExit("question is required unless --generate-examples is used")

    state = run_framework_agent(args.question)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print_text_result(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
