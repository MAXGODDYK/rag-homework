from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_GOAL_LENGTH = 1000

Language = Literal["uk", "ru", "en"]
Route = Literal[
    "exam_preparation",
    "daily_routine",
    "combined_planning",
    "clarification",
]
TracePhase = Literal[
    "validation",
    "routing",
    "action",
    "observation",
    "finalization",
]


class ToolCall(BaseModel):
    sequence: int
    tool_name: str
    arguments: dict[str, Any]
    status: Literal["completed"] = "completed"


class Observation(BaseModel):
    sequence: int
    tool_name: str
    result: dict[str, Any]


class StateSnapshot(BaseModel):
    step: int
    phase: TracePhase
    current_step: str
    selected_route: Route | None
    tool_call_count: int
    observation_count: int
    message: str
    tool_name: str | None = None


class AgentState(BaseModel):
    user_goal: str
    language: Language
    selected_route: Route | None = None
    current_step: str = "initialized"
    tool_calls: list[ToolCall] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    state_history: list[StateSnapshot] = Field(default_factory=list)
    needs_clarification: bool = False
    final_answer: str = ""


EXAM_KEYWORDS = (
    "іспит",
    "екзамен",
    "підготов",
    "навчан",
    "тест",
    "экзамен",
    "подготов",
    "учеб",
    "exam",
    "prepare",
    "preparation",
    "study",
    "test",
)

ROUTINE_KEYWORDS = (
    "режим",
    "розпоряд",
    "распоряд",
    "сон",
    "спати",
    "спать",
    "відпоч",
    "отдых",
    "перерв",
    "перерыв",
    "баланс",
    "routine",
    "schedule",
    "sleep",
    "rest",
    "break",
    "balance",
)


def validate_goal(user_goal: str) -> str:
    normalized = user_goal.strip()
    if not normalized:
        raise ValueError("User goal не може бути порожнім")
    if len(normalized) > MAX_GOAL_LENGTH:
        raise ValueError(
            f"User goal перевищує максимум {MAX_GOAL_LENGTH} символів"
        )
    return normalized


def detect_language(text: str) -> Language:
    lowered = text.lower()
    if any(character in lowered for character in "іїєґ"):
        return "uk"
    if any(character in lowered for character in "ыэёъ"):
        return "ru"
    russian_markers = (
        "как ",
        "мне ",
        "нужно",
        "организ",
        "отдых",
        "между",
        "занят",
        "распоряд",
        "экзамен",
        "учеб",
    )
    if any(marker in lowered for marker in russian_markers):
        return "ru"
    if any("a" <= character <= "z" for character in lowered):
        return "en"
    return "uk"


def route_goal(user_goal: str) -> Route:
    lowered = user_goal.lower()
    has_exam_intent = any(word in lowered for word in EXAM_KEYWORDS)
    has_routine_intent = any(word in lowered for word in ROUTINE_KEYWORDS)

    if has_exam_intent and has_routine_intent:
        return "combined_planning"
    if has_exam_intent:
        return "exam_preparation"
    if has_routine_intent:
        return "daily_routine"
    return "clarification"


def mock_get_exam_plan(language: Language) -> dict[str, Any]:
    plans = {
        "uk": [
            "День 1: визначити мету та перелік тем.",
            "День 2: повторити перший блок матеріалу.",
            "День 3: повторити другий блок матеріалу.",
            "День 4: виконати практичні завдання.",
            "День 5: пройти пробний тест.",
            "День 6: опрацювати помилки та слабкі теми.",
            "День 7: коротке повторення і повноцінний відпочинок.",
        ],
        "ru": [
            "День 1: определить цель и список тем.",
            "День 2: повторить первый блок материала.",
            "День 3: повторить второй блок материала.",
            "День 4: выполнить практические задания.",
            "День 5: пройти пробный тест.",
            "День 6: разобрать ошибки и слабые темы.",
            "День 7: короткое повторение и полноценный отдых.",
        ],
        "en": [
            "Day 1: define the goal and list the topics.",
            "Day 2: review the first material block.",
            "Day 3: review the second material block.",
            "Day 4: complete practice tasks.",
            "Day 5: take a mock test.",
            "Day 6: review mistakes and weak topics.",
            "Day 7: do a short review and get proper rest.",
        ],
    }
    return {
        "result_type": "mock",
        "duration_days": 7,
        "plan": plans[language],
    }


def mock_get_daily_routine(language: Language) -> dict[str, Any]:
    labels = {
        "uk": {
            "morning": "Підйом, сніданок і визначення пріоритетів",
            "focus": "Перша сфокусована навчальна сесія",
            "break": "Перерва, рух і відпочинок від екрана",
            "practice": "Друга сесія: практика та перевірка знань",
            "review": "Коротке підбиття підсумків і план на завтра",
            "sleep": "Сон",
        },
        "ru": {
            "morning": "Подъём, завтрак и определение приоритетов",
            "focus": "Первая сфокусированная учебная сессия",
            "break": "Перерыв, движение и отдых от экрана",
            "practice": "Вторая сессия: практика и проверка знаний",
            "review": "Краткое подведение итогов и план на завтра",
            "sleep": "Сон",
        },
        "en": {
            "morning": "Wake up, have breakfast, and set priorities",
            "focus": "First focused study session",
            "break": "Take a break, move, and rest from the screen",
            "practice": "Second session: practice and knowledge check",
            "review": "Brief review and plan for tomorrow",
            "sleep": "Sleep",
        },
    }[language]
    return {
        "result_type": "mock",
        "sleep_hours": 8,
        "focus_block_minutes": 50,
        "break_minutes": 10,
        "schedule": [
            {"time": "08:00", "activity": labels["morning"]},
            {"time": "09:00", "activity": labels["focus"]},
            {"time": "09:50", "activity": labels["break"]},
            {"time": "10:00", "activity": labels["practice"]},
            {"time": "18:00", "activity": labels["review"]},
            {"time": "23:00", "activity": labels["sleep"]},
        ],
    }


def _record_transition(
    state: AgentState,
    phase: TracePhase,
    message: str,
    *,
    tool_name: str | None = None,
) -> None:
    state.state_history.append(
        StateSnapshot(
            step=len(state.state_history) + 1,
            phase=phase,
            current_step=state.current_step,
            selected_route=state.selected_route,
            tool_call_count=len(state.tool_calls),
            observation_count=len(state.observations),
            message=message,
            tool_name=tool_name,
        )
    )


def _execute_tool(state: AgentState, tool_name: str) -> None:
    sequence = len(state.tool_calls) + 1
    state.current_step = f"calling:{tool_name}"
    state.tool_calls.append(
        ToolCall(
            sequence=sequence,
            tool_name=tool_name,
            arguments={"language": state.language},
        )
    )
    _record_transition(
        state,
        "action",
        f"Виклик deterministic mock tool: {tool_name}",
        tool_name=tool_name,
    )

    if tool_name == "mock_get_exam_plan":
        result = mock_get_exam_plan(state.language)
    elif tool_name == "mock_get_daily_routine":
        result = mock_get_daily_routine(state.language)
    else:
        raise ValueError(f"Невідомий agent tool: {tool_name}")

    state.observations.append(
        Observation(
            sequence=sequence,
            tool_name=tool_name,
            result=result,
        )
    )
    state.current_step = f"observed:{tool_name}"
    _record_transition(
        state,
        "observation",
        f"Результат {tool_name} збережено в observations",
        tool_name=tool_name,
    )


def _format_exam_answer(result: dict[str, Any], language: Language) -> str:
    headings = {
        "uk": "План підготовки на 7 днів:",
        "ru": "План подготовки на 7 дней:",
        "en": "Seven-day preparation plan:",
    }
    return "\n".join(
        [headings[language], *[f"- {item}" for item in result["plan"]]]
    )


def _format_routine_answer(result: dict[str, Any], language: Language) -> str:
    headings = {
        "uk": "Приклад збалансованого навчального дня:",
        "ru": "Пример сбалансированного учебного дня:",
        "en": "Example of a balanced study day:",
    }
    lines = [headings[language]]
    lines.extend(
        f"- {item['time']}: {item['activity']}"
        for item in result["schedule"]
    )
    return "\n".join(lines)


def _build_final_answer(state: AgentState) -> str:
    if state.selected_route == "clarification":
        messages = {
            "uk": (
                "Уточніть, будь ласка: вам потрібен план підготовки "
                "до іспиту, розпорядок навчального дня чи обидва варіанти?"
            ),
            "ru": (
                "Уточните, пожалуйста: вам нужен план подготовки к "
                "экзамену, распорядок учебного дня или оба варианта?"
            ),
            "en": (
                "Please clarify whether you need an exam preparation "
                "plan, a daily study routine, or both."
            ),
        }
        return messages[state.language]

    answers: list[str] = []
    for observation in state.observations:
        if observation.tool_name == "mock_get_exam_plan":
            answers.append(
                _format_exam_answer(observation.result, state.language)
            )
        elif observation.tool_name == "mock_get_daily_routine":
            answers.append(
                _format_routine_answer(observation.result, state.language)
            )
    return "\n\n".join(answers)


def run_agent(user_goal: str) -> AgentState:
    goal = validate_goal(user_goal)
    state = AgentState(
        user_goal=goal,
        language=detect_language(goal),
    )

    state.current_step = "validated"
    _record_transition(state, "validation", "User goal пройшов validation")

    state.selected_route = route_goal(goal)
    state.current_step = "routed"
    _record_transition(
        state,
        "routing",
        f"Обрано route: {state.selected_route}",
    )

    if state.selected_route == "exam_preparation":
        _execute_tool(state, "mock_get_exam_plan")
    elif state.selected_route == "daily_routine":
        _execute_tool(state, "mock_get_daily_routine")
    elif state.selected_route == "combined_planning":
        _execute_tool(state, "mock_get_exam_plan")
        _execute_tool(state, "mock_get_daily_routine")
    else:
        state.needs_clarification = True

    state.final_answer = _build_final_answer(state)
    state.current_step = "completed"
    _record_transition(
        state,
        "finalization",
        "Final answer сформовано; workflow завершено",
    )
    return state


EXAMPLE_QUESTIONS = (
    "Як скласти план підготовки до іспиту?",
    "Як організувати режим дня, сон і перерви?",
    "Create an exam study plan that includes sleep and breaks.",
    "Как организовать режим дня и отдых между занятиями?",
    "Розкажи щось корисне.",
)


def render_example_report(states: list[AgentState]) -> str:
    lines = [
        "# HW6 — Agent flow examples",
        "",
        "Усі приклади згенеровано реальним deterministic workflow без LLM та API.",
        "",
    ]
    for number, state in enumerate(states, start=1):
        tool_names = [call.tool_name for call in state.tool_calls]
        observations = [item.model_dump(mode="json") for item in state.observations]
        history = [item.model_dump(mode="json") for item in state.state_history]
        lines.extend(
            [
                f"## {number}. {state.selected_route}",
                "",
                f"**Question:** {state.user_goal}",
                "",
                f"**Route:** `{state.selected_route}`",
                "",
                "**Tool called:** "
                + (", ".join(f"`{name}`" for name in tool_names) or "none"),
                "",
                "**Observation:**",
                "",
                "```json",
                json.dumps(observations, ensure_ascii=False, indent=2),
                "```",
                "",
                "**State after steps:**",
                "",
                "```json",
                json.dumps(history, ensure_ascii=False, indent=2),
                "```",
                "",
                "**Final answer:**",
                "",
                state.final_answer,
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def generate_examples(output_path: Path) -> list[AgentState]:
    states = [run_agent(question) for question in EXAMPLE_QUESTIONS]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_example_report(states),
        encoding="utf-8",
    )
    return states


def print_text_result(state: AgentState) -> None:
    print("=============== AGENT FLOW ===============")
    print(f"Question: {state.user_goal}")
    print(f"Language: {state.language}")
    print(f"Route: {state.selected_route}")

    print("\n=============== TRACE ===============")
    for snapshot in state.state_history:
        tool = f" | tool={snapshot.tool_name}" if snapshot.tool_name else ""
        print(
            f"Step {snapshot.step}: {snapshot.phase} | "
            f"state={snapshot.current_step}{tool}"
        )
        print(f"  {snapshot.message}")

    print("\n=============== FINAL STATE ===============")
    print(json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print("\n=============== FINAL ANSWER ===============")
    print(state.final_answer)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic student-planning agent workflow",
    )
    parser.add_argument("question", nargs="?")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print only the complete machine-readable AgentState",
    )
    parser.add_argument(
        "--generate-examples",
        action="store_true",
        help="Generate outputs/agent_flow_examples.md",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "agent_flow_examples.md",
        help="Report path used with --generate-examples",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.generate_examples:
            states = generate_examples(args.output)
            print(f"Report: {args.output.resolve()}")
            print(f"Examples: {len(states)}")
            return 0
        if args.question is None:
            parser.error("question is required unless --generate-examples is used")

        state = run_agent(args.question)
        if args.json:
            print(state.model_dump_json(indent=2))
        else:
            print_text_result(state)
        return 0
    except ValueError as error:
        print(f"Validation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
