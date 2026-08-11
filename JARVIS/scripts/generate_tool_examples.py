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
from scripts.tools.orchestrator import ExternalToolOrchestrator
from scripts.tools.schemas import ExchangeRateInput, kyiv_today


OUTPUT_PATH = PROJECT_ROOT / "outputs" / "tool_examples.md"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _success_example(
    number: int,
    title: str,
    question: str,
    answer,
    reason: str,
) -> str:
    return "\n".join(
        [
            f"## {number}. {title}",
            "",
            f"**User question:** {question}",
            "",
            f"**Tool called:** `{answer.tool_name}`",
            "",
            "**Input:**",
            "",
            "```json",
            _json(answer.tool_input.model_dump(mode="json")),
            "```",
            "",
            "**Result:**",
            "",
            "```json",
            _json(answer.result.model_dump(mode="json")),
            "```",
            "",
            f"**Final answer:** {answer.answer}",
            "",
            f"**Why tool is better than retrieval:** {reason}",
            "",
        ]
    )


def build_report(provider_name: str) -> str:
    settings = load_settings()
    orchestrator = ExternalToolOrchestrator(
        providers=build_text_providers(settings)
    )
    today = kyiv_today().isoformat()

    usd_question = "Який офіційний курс USD сьогодні?"
    usd = orchestrator.answer_direct(
        {"currency_code": "USD"},
        usd_question,
    )
    eur_question = "Скільки гривень потрібно для 100 EUR сьогодні?"
    eur = orchestrator.answer_direct(
        {"currency_code": "EUR", "amount": 100},
        eur_question,
    )
    pln_question = "Який був офіційний курс PLN 1 серпня 2026 року?"
    pln = orchestrator.answer_direct(
        {
            "currency_code": "PLN",
            "amount": 1,
            "date": "2026-08-01",
        },
        pln_question,
    )
    gbp_question = "How much is 50 GBP in UAH at today's official NBU rate?"
    gbp = orchestrator.try_answer(gbp_question, provider_name)
    if gbp is None:
        raise RuntimeError("LLM router unexpectedly selected RAG for GBP")

    invalid_input = {"currency_code": "US", "amount": 1}
    try:
        ExchangeRateInput.model_validate(invalid_input)
    except ValidationError as error:
        invalid_reason = error.errors(include_url=False)[0]["msg"]
    else:
        raise RuntimeError("Invalid currency code unexpectedly passed")

    rag_question = "Як скласти реалістичний план підготовки до іспиту?"
    rag_decision = orchestrator.try_answer(rag_question, provider_name)
    if rag_decision is not None:
        raise RuntimeError("Prefilter unexpectedly routed study question to NBU")

    sections = [
        "# HW5 — External NBU tool: real examples",
        "",
        f"Generated: `{today}` (Europe/Kyiv).",
        "",
        (
            "The tool is read-only and uses the fixed official NBU HTTPS "
            "endpoint. It does not require an API key or confirmation."
        ),
        "",
        _success_example(
            1,
            "Current USD rate",
            usd_question,
            usd,
            "The local knowledge base cannot contain a current official rate.",
        ),
        _success_example(
            2,
            "Convert 100 EUR to UAH",
            eur_question,
            eur,
            "NBU provides the authoritative rate and Decimal performs the calculation.",
        ),
        _success_example(
            3,
            "Historical PLN rate",
            pln_question,
            pln,
            "The requested historical date is explicit and independently verifiable.",
        ),
        _success_example(
            4,
            "English GBP request through LLM router",
            gbp_question,
            gbp,
            (
                "The router extracts validated parameters, while the final number "
                "still comes only from NBU and is formatted deterministically."
            ),
        ),
        "## 5. Invalid currency code rejected before HTTP",
        "",
        "**User question:** `/rate US`",
        "",
        "**Tool called:** no",
        "",
        "**Input:**",
        "",
        "```json",
        _json(invalid_input),
        "```",
        "",
        f"**Result:** Pydantic validation error: {invalid_reason}",
        "",
        "**Final answer:** The request is rejected with `/rate` usage guidance.",
        "",
        (
            "**Why tool is better than retrieval:** validation prevents an invalid "
            "external call; retrieval cannot validate an API input contract."
        ),
        "",
        "## RAG control example",
        "",
        f"**User question:** {rag_question}",
        "",
        "**Router decision:** `rag` (currency prefilter did not call the LLM router).",
        "",
        "**NBU tool called:** no.",
        "",
        (
            "This confirms that ordinary study questions continue through the "
            "existing grounded RAG pipeline."
        ),
        "",
    ]
    return "\n".join(sections)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=("openai", "freemodel", "local"),
        default="freemodel",
    )
    args = parser.parse_args()
    report = build_report(args.provider)
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Saved: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
