from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import load_settings
from scripts.rag.providers import build_text_providers
from scripts.tools.orchestrator import (
    ExternalToolOrchestrator,
    format_external_tool_answer,
)
from scripts.tools.schemas import (
    ExchangeRateInput,
    ExternalToolError,
    ToolRoutingError,
)


def print_section(title: str) -> None:
    print(f"\n=============== {title} ===============")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only official NBU exchange-rate tool",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    call_parser = subparsers.add_parser(
        "call",
        help="Call the NBU tool with validated explicit arguments",
    )
    call_parser.add_argument("--currency", required=True)
    call_parser.add_argument("--amount", default="1")
    call_parser.add_argument("--date")

    route_parser = subparsers.add_parser(
        "route",
        help="Route a natural-language question through an LLM",
    )
    route_parser.add_argument("question")
    route_parser.add_argument(
        "--provider",
        choices=("openai", "freemodel", "local"),
        default="freemodel",
    )
    return parser


def run_call(args: argparse.Namespace) -> int:
    tool_input = ExchangeRateInput.model_validate(
        {
            "currency_code": args.currency,
            "amount": args.amount,
            "date": args.date,
        }
    )
    settings = load_settings()
    orchestrator = ExternalToolOrchestrator(
        providers=build_text_providers(settings)
    )
    result = orchestrator.answer_direct(
        tool_input,
        question=f"Офіційний курс {tool_input.currency_code}",
    )

    print_section("VALIDATED INPUT")
    print(json.dumps(tool_input.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print_section("NORMALIZED RESULT")
    print(json.dumps(result.result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print_section("FINAL ANSWER")
    print(format_external_tool_answer(result))
    return 0


def run_route(args: argparse.Namespace) -> int:
    question = args.question.strip()
    if not question:
        raise ValueError("Question не може бути порожнім")

    settings = load_settings()
    orchestrator = ExternalToolOrchestrator(
        providers=build_text_providers(settings)
    )
    print_section("ROUTER")
    answer = orchestrator.try_answer(question, args.provider)
    if answer is None:
        print("Decision: rag")
        print("NBU tool was not called.")
        return 0

    print(f"Decision: {answer.tool_name}")
    print(f"Provider: {answer.router_provider}")
    print("Input:")
    print(json.dumps(answer.tool_input.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print_section("NORMALIZED RESULT")
    print(json.dumps(answer.result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print_section("FINAL ANSWER")
    print(format_external_tool_answer(answer))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.mode == "call":
            return run_call(args)
        return run_route(args)
    except ValidationError as error:
        print_section("VALIDATION ERROR")
        for item in error.errors(include_url=False):
            field = ".".join(str(part) for part in item["loc"])
            print(f"- {field}: {item['msg']}")
        return 2
    except (ExternalToolError, ToolRoutingError, ValueError) as error:
        print_section("SAFE ERROR")
        print(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
