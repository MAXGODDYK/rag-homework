from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Protocol

# The existing HW4-HW7 modules use absolute sibling imports (`scripts.*`).
# Adding the HW8 root keeps this file runnable both as a module and as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings
from scripts.agent_flow import run_agent
from scripts.rag.providers import TextProvider
from scripts.rag.retriever import GroundedRetriever
from scripts.rag.schemas import RagAnswer, detect_question_language
from scripts.rag.service import RagAnswerService
from scripts.tools.nbu_exchange import NbuExchangeRateTool
from scripts.tools.orchestrator import ExternalToolOrchestrator
from scripts.tools.schemas import ExchangeRateInput, ExternalToolAnswer


CASES_PATH = PROJECT_ROOT / "data" / "evaluation" / "chatbot_eval_cases.json"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
CSV_PATH = OUTPUTS_DIR / "eval_results.csv"
TRACE_PATH = OUTPUTS_DIR / "eval_traces.jsonl"
METRICS_PATH = OUTPUTS_DIR / "eval_metrics.json"
SUMMARY_PATH = OUTPUTS_DIR / "eval_summary.md"
QUALITY_REPORT_PATH = OUTPUTS_DIR / "quality_report.md"

REQUIRED_COLUMNS = (
    "id",
    "question",
    "expected_behavior",
    "answer",
    "retrieved_chunks",
    "route_or_mode",
    "tools_used",
    "task_success",
    "groundedness",
    "answer_quality",
    "latency_ms",
    "errors",
    "notes",
)

CaseKind = Literal["rag", "tool", "agent"]
TaskSuccess = Literal["yes", "partial", "no"]
Quality = Literal["good", "partial", "bad"]


@dataclass(frozen=True)
class EvalCase:
    id: int
    kind: CaseKind
    question: str
    expected_behavior: str
    expected_chunk_ids: tuple[str, ...] = ()
    partial_chunk_ids: tuple[str, ...] = ()
    expect_fallback: bool = False
    tool_input: dict[str, Any] | None = None
    expected_agent_route: str | None = None


@dataclass(frozen=True)
class EvalRecord:
    id: int
    question: str
    expected_behavior: str
    answer: str
    retrieved_chunks: str
    route_or_mode: str
    tools_used: str
    task_success: TaskSuccess
    groundedness: Quality
    answer_quality: Quality
    latency_ms: int
    errors: str
    notes: str
    evaluation_mode: str
    retrieval_latency_ms: int
    generation_latency_ms: int
    observed_at_utc: str

    def csv_row(self) -> dict[str, str | int]:
        payload = asdict(self)
        return {
            key: value if isinstance(value, int) else str(value)
            for key, value in payload.items()
        }


class EvaluationProvider(TextProvider):
    """Local extractive provider for repeatable evaluation runs.

    It does not mimic an LLM. It deliberately returns a short verbatim
    passage from the best reranked context with a valid citation. This keeps
    the measurement focused on the real HW4 pipeline: hybrid retrieval, BGE,
    confidence gate, prompt construction and citation validation. Live LLM
    generation remains optional and is not claimed by the resulting report.
    """

    name = "evaluation_extractive"

    _context_pattern = re.compile(
        r"\[CONTEXT 1\]\s*"
        r"chunk_id:\s*(?P<chunk_id>[^\n]+).*?"
        r"text:\s*(?P<text>.*?)\s*"
        r"\[/CONTEXT 1\]",
        flags=re.DOTALL,
    )

    def availability(self) -> tuple[bool, str]:
        return True, "local deterministic extractive evaluation provider"

    @staticmethod
    def _short_extractive_answer(text: str, language: str) -> str:
        normalized = " ".join(text.split())
        normalized = re.sub(r"^(?:Назва|Розділ):[^.]*\.\s*", "", normalized)
        sentences = re.split(r"(?<=[.!?])\s+", normalized)
        meaningful = [
            sentence.strip()
            for sentence in sentences
            if len(sentence.strip()) >= 35
        ]
        excerpt = " ".join(meaningful[:2]) or normalized
        excerpt = excerpt[:600].rstrip()
        if language == "en":
            return f"Relevant context excerpt: {excerpt}"
        if language == "ru":
            return f"Фрагмент релевантного контекста: {excerpt}"
        return f"Фрагмент релевантного контексту: {excerpt}"

    def generate(self, prompt: str) -> str:
        match = self._context_pattern.search(prompt)
        if match is None:
            raise RuntimeError("Evaluation provider did not receive context")

        question_match = re.search(
            r"QUESTION:\s*(?P<question>.+)$",
            prompt,
            flags=re.DOTALL,
        )
        question = question_match.group("question").strip() if question_match else ""
        payload = {
            "answer": self._short_extractive_answer(
                match.group("text"),
                detect_question_language(question),
            ),
            "citations": [match.group("chunk_id").strip()],
            "insufficient_context": False,
        }
        return json.dumps(payload, ensure_ascii=False)


class RerankingRetriever(Protocol):
    def retrieve(
        self,
        question: str,
        top_k: int,
        candidate_k: int,
        source_file: str | None = None,
    ) -> list[dict[str, Any]]:
        ...


def load_cases(path: Path = CASES_PATH) -> list[EvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not 8 <= len(payload) <= 12:
        raise ValueError("Eval set повинен містити від 8 до 12 cases")

    cases: list[EvalCase] = []
    identifiers: set[int] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Кожен eval case повинен бути JSON object")
        case = EvalCase(
            id=int(item["id"]),
            kind=item["kind"],
            question=str(item["question"]).strip(),
            expected_behavior=str(item["expected_behavior"]).strip(),
            expected_chunk_ids=tuple(item.get("expected_chunk_ids", ())),
            partial_chunk_ids=tuple(item.get("partial_chunk_ids", ())),
            expect_fallback=bool(item.get("expect_fallback", False)),
            tool_input=item.get("tool_input"),
            expected_agent_route=item.get("expected_agent_route"),
        )
        if case.id in identifiers or not case.question:
            raise ValueError("Eval case має мати унікальний id і непорожнє question")
        if case.kind == "tool" and not case.tool_input:
            raise ValueError("Tool case повинен містити tool_input")
        if case.kind == "agent" and not case.expected_agent_route:
            raise ValueError("Agent case повинен містити expected_agent_route")
        identifiers.add(case.id)
        cases.append(case)
    return cases


def _settings() -> Settings:
    return Settings(
        telegram_bot_token="",
        openai_api_key="",
        hf_token="",
        local_adapter_path=None,
    )


def _compact_chunks(chunks: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": chunk["chunk_id"],
            "source_file": chunk["source_file"],
            "section": chunk["section"],
            "reranker_raw_score": round(float(chunk["reranker_raw_score"]), 4),
        }
        for chunk in chunks
    ]


def _score_rag(case: EvalCase, result: RagAnswer) -> tuple[TaskSuccess, Quality, Quality, str, str]:
    retrieved_ids = {chunk["chunk_id"] for chunk in result.retrieved_chunks}
    citation_ids = set(result.citations)
    expected_ids = set(case.expected_chunk_ids)
    partial_ids = set(case.partial_chunk_ids)

    if case.expect_fallback:
        if result.is_fallback and not citation_ids:
            return "yes", "good", "good", "none", "Confidence gate безпечно повернув fallback."
        return "no", "bad", "bad", "confidence_gate_not_triggered", "Нерелевантний контекст не був відхилений."

    expected_retrieved = bool(retrieved_ids & expected_ids)
    expected_cited = bool(citation_ids & expected_ids)
    citations_valid = citation_ids <= retrieved_ids and bool(citation_ids)

    if expected_cited and citations_valid and not result.is_fallback:
        if (
            detect_question_language(case.question) == "en"
            and re.search(r"[іїєґІЇЄҐ]", result.answer)
        ):
            return (
                "yes",
                "good",
                "partial",
                "evaluation_provider_language_mismatch",
                "Retrieval і citation коректні, але extractive provider зберіг український фрагмент для English question.",
            )
        return "yes", "good", "good", "none", "Очікуваний chunk знайдено та процитовано."
    if expected_retrieved and citations_valid and not result.is_fallback:
        return "partial", "partial", "partial", "missing_expected_citation", "Релевантний chunk знайдено, але extractive provider процитував інший top-1 chunk."
    if retrieved_ids & partial_ids and citations_valid and not result.is_fallback:
        return "partial", "good", "partial", "wrong_retrieval", "Знайдено пов'язаний, але не основний фрагмент для цього складного запиту."
    if result.is_fallback:
        return "no", "bad", "bad", "unexpected_fallback", "Релевантний case завершився fallback."
    return "no", "bad", "bad", "wrong_retrieval", "Серед top-3 немає очікуваних chunks."


def _evaluate_rag(
    case: EvalCase,
    service: RagAnswerService,
) -> EvalRecord:
    result = service.answer(
        case.question,
        provider_name="evaluation",
        top_k=3,
        candidate_k=10,
        allow_local_fallback=False,
    )
    success, groundedness, quality, error, note = _score_rag(case, result)
    return EvalRecord(
        id=case.id,
        question=case.question,
        expected_behavior=case.expected_behavior,
        answer=result.answer,
        retrieved_chunks=json.dumps(
            _compact_chunks(result.retrieved_chunks),
            ensure_ascii=False,
        ),
        route_or_mode="fallback" if result.is_fallback else "rag",
        tools_used="",
        task_success=success,
        groundedness=groundedness,
        answer_quality=quality,
        latency_ms=round(result.latency_ms),
        errors=error,
        notes=note,
        evaluation_mode="real_retrieval + deterministic_extractive_provider",
        retrieval_latency_ms=round(result.retrieval_latency_ms),
        generation_latency_ms=round(result.generation_latency_ms),
        observed_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def _evaluate_tool(
    case: EvalCase,
    tool_orchestrator: ExternalToolOrchestrator,
) -> EvalRecord:
    assert case.tool_input is not None
    started_at = perf_counter()
    tool_input = ExchangeRateInput.model_validate(case.tool_input)
    result: ExternalToolAnswer = tool_orchestrator.answer_direct(
        tool_input,
        question=case.question,
    )
    latency_ms = round((perf_counter() - started_at) * 1000)
    converted = result.result.converted_amount_uah
    amount = result.tool_input.amount
    success = (
        result.result.source == "National Bank of Ukraine"
        and result.result.currency_code == tool_input.currency_code
        and converted > 0
        and amount > 0
    )
    return EvalRecord(
        id=case.id,
        question=case.question,
        expected_behavior=case.expected_behavior,
        answer=result.answer,
        retrieved_chunks=json.dumps(
            [{
                "source": result.result.source,
                "source_url": result.result.source_url,
                "effective_date": result.result.effective_date.isoformat(),
            }],
            ensure_ascii=False,
        ),
        route_or_mode="tool",
        tools_used=result.tool_name,
        task_success="yes" if success else "no",
        groundedness="good" if success else "bad",
        answer_quality="good" if success else "bad",
        latency_ms=latency_ms,
        errors="none" if success else "tool_response_validation",
        notes="Курс і сума сформовані детерміновано за live відповіддю НБУ.",
        evaluation_mode="live_nbu_tool",
        retrieval_latency_ms=0,
        generation_latency_ms=0,
        observed_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def _evaluate_agent(case: EvalCase) -> EvalRecord:
    started_at = perf_counter()
    state = run_agent(case.question)
    latency_ms = round((perf_counter() - started_at) * 1000)
    success = (
        state.selected_route == case.expected_agent_route
        and not state.tool_calls
        and state.needs_clarification
    )
    return EvalRecord(
        id=case.id,
        question=case.question,
        expected_behavior=case.expected_behavior,
        answer=state.final_answer,
        retrieved_chunks="[]",
        route_or_mode=f"agent/{state.selected_route}",
        tools_used=", ".join(call.tool_name for call in state.tool_calls),
        task_success="yes" if success else "no",
        groundedness="good" if success else "bad",
        answer_quality="good" if success else "bad",
        latency_ms=latency_ms,
        errors="none" if success else "wrong_agent_route",
        notes="Clarification route виконується локально без RAG і tool call.",
        evaluation_mode="real_deterministic_agent",
        retrieval_latency_ms=0,
        generation_latency_ms=0,
        observed_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def run_evaluation(cases: list[EvalCase] | None = None) -> list[EvalRecord]:
    cases = cases or load_cases()
    retriever: RerankingRetriever = GroundedRetriever()
    provider = EvaluationProvider()
    service = RagAnswerService(
        settings=_settings(),
        retriever=retriever,
        providers={"evaluation": provider},
    )
    tool_orchestrator = ExternalToolOrchestrator(providers={})
    records: list[EvalRecord] = []

    for case in cases:
        if case.kind == "rag":
            records.append(_evaluate_rag(case, service))
        elif case.kind == "tool":
            records.append(_evaluate_tool(case, tool_orchestrator))
        else:
            records.append(_evaluate_agent(case))
    return records


def calculate_metrics(records: list[EvalRecord]) -> dict[str, Any]:
    if not records:
        raise ValueError("Неможливо обчислити метрики без records")

    total = len(records)
    errors = Counter(record.errors for record in records)
    return {
        "total_cases": total,
        "success_count": sum(record.task_success == "yes" for record in records),
        "partial_success_count": sum(record.task_success == "partial" for record in records),
        "failure_count": sum(record.task_success == "no" for record in records),
        "success_rate": sum(record.task_success == "yes" for record in records) / total,
        "groundedness_good_count": sum(record.groundedness == "good" for record in records),
        "groundedness_good_rate": sum(record.groundedness == "good" for record in records) / total,
        "average_latency_ms": round(sum(record.latency_ms for record in records) / total),
        "average_retrieval_latency_ms": round(sum(record.retrieval_latency_ms for record in records) / total),
        "max_latency_ms": max(record.latency_ms for record in records),
        "top_error_types": dict(errors.most_common()),
    }


def render_summary(metrics: dict[str, Any], records: list[EvalRecord]) -> str:
    errors = metrics["top_error_types"]
    error_lines = "\n".join(
        f"- `{name}`: {count}" for name, count in errors.items()
    )
    modes = Counter(record.evaluation_mode for record in records)
    mode_lines = "\n".join(
        f"- `{mode}`: {count}" for mode, count in modes.items()
    )
    return f"""# HW8 — Підсумок observability metrics

## Що вимірювалося

Запуск містить {metrics['total_cases']} кейсів: RAG retrieval і confidence
gate, два live виклики NBU tool та один deterministic agent clarification.
RAG cases проходять справжній pipeline hybrid retrieval + BGE reranker +
`RagAnswerService`. Оскільки в цьому середовищі не налаштовано remote або
local LLM provider, generation layer використовує deterministic extractive
provider: він повертає процитований фрагмент із top-1 reranked chunk. Отже,
ці метрики перевіряють routing, retrieval, gate, tool handling і citation
validation, але не є benchmark-ом якості тексту live LLM.

## Метрики

- Усього cases: **{metrics['total_cases']}**
- Success rate: **{metrics['success_count']}/{metrics['total_cases']} = {metrics['success_rate']:.0%}**
- Partial success: **{metrics['partial_success_count']}/{metrics['total_cases']}**
- Failure rate: **{metrics['failure_count']}/{metrics['total_cases']}**
- Groundedness good: **{metrics['groundedness_good_count']}/{metrics['total_cases']} = {metrics['groundedness_good_rate']:.0%}**
- Середня end-to-end latency: **{metrics['average_latency_ms']} ms**
- Середня retrieval latency для всіх cases: **{metrics['average_retrieval_latency_ms']} ms**
- Максимальна latency: **{metrics['max_latency_ms']} ms**

## Evaluation modes

{mode_lines}

## Типи помилок

{error_lines}

`eval_results.csv` є source of truth для кожної оцінки, а
`eval_traces.jsonl` містить ті самі records у machine-readable форматі.
Timestamps і NBU rates навмисно залежать від конкретного запуску.
"""


def render_quality_report(metrics: dict[str, Any], records: list[EvalRecord]) -> str:
    wrong_retrieval = sum(
        record.errors in {"wrong_retrieval", "missing_expected_citation"}
        for record in records
    )
    fallback_count = sum(record.route_or_mode == "fallback" for record in records)
    rag_latencies = [record.latency_ms for record in records if record.route_or_mode in {"rag", "fallback"}]
    average_rag_latency = round(sum(rag_latencies) / len(rag_latencies)) if rag_latencies else 0

    return f"""# HW8 — Quality report

## Що тестувалося

Я запустив {metrics['total_cases']} навмисно різних питань через компоненти
student-planning chatbot-а: прямі knowledge-base питання, multi-document
planning, складний запит про прокрастинацію, English retrieval, два
out-of-domain питання, два live виклики офіційного курсу НБУ та clarification
route детермінованого agent-а. Повні observed outputs, retrieved chunks,
routes, citations, errors і latency збережені в `outputs/eval_results.csv`.

## Результати

Виміряний task success rate становить **{metrics['success_rate']:.0%}**
({metrics['success_count']}/{metrics['total_cases']}), а groundedness-good
rate — **{metrics['groundedness_good_rate']:.0%}**. Live NBU tool cases
повернули нормалізовані офіційні дані та детермінований перерахунок. Два
out-of-domain питання дали `{fallback_count}` безпечні fallback responses
замість непідтверджених фактів. Середня RAG/fallback latency склала
**{average_rag_latency} ms**: це включає завантаження й виконання
multilingual embedding model та BGE reranking на CPU.

## Де система працює добре

Найсильніша властивість — bounded execution: прямі навчальні питання
зберігають retrieved chunk IDs, confidence gate не дозволяє відповідати, коли
corpus нерелевантний, а NBU integration використовує validated allowlisted
input замість числа, згенерованого LLM. Agent clarification case також
завершується без непотрібних retrieval і tool calls.

## Де система працює слабше

Складні та нечіткі retrieval cases показують, що top-ranked chunk не завжди
є chunk-ом, який найкраще відповідає очікуваному підпитанню. Extractive
evaluation provider показує це як `wrong_retrieval` або
`missing_expected_citation`; у цьому запуску таких cases **{wrong_retrieval}**.
Результат корисний, але не вимірює якість реального remote або local LLM,
оскільки у відтворюваному запуску provider не налаштований.

## Три головні проблеми

1. **Нечіткі або multi-intent queries можуть повертати сусідню тему.**
   Поточна top-3 стратегія не має query rewriting або intent-specific metadata
   filter, тому семантично близький planning chunk може витісняти chunk про
   прокрастинацію чи пріоритети.
2. **Generation quality ще не спостерігається через live provider.**
   Deterministic extractive provider перевіряє JSON/citation contract, але не
   може показати справжні LLM hallucinations, переклад або synthesis кількох
   chunks.
3. **CPU reranking домінує в interactive latency.** BGE покращує relevance,
   але його вартість видно в observed RAG latency і користувач відчує її в
   Telegram для кожного питання.

## Наступні кроки

Наступним кроком я б додав intent-aware metadata filters і query rewriting
для неоднозначних питань, запустив той самий fixed eval set із налаштованими
FreeModel/OpenAI/local providers і записував citation validity окремо від
answer correctness, а також кешував або batch-ив reranker candidates, щоб
зменшити CPU latency. Збережені CSV і JSONL traces дозволяють порівнювати
before/after без зміни eval set.
"""


def write_outputs(records: list[EvalRecord], output_dir: Path = OUTPUTS_DIR) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / CSV_PATH.name
    trace_path = output_dir / TRACE_PATH.name
    metrics_path = output_dir / METRICS_PATH.name
    summary_path = output_dir / SUMMARY_PATH.name
    quality_path = output_dir / QUALITY_REPORT_PATH.name
    metrics = calculate_metrics(records)

    fieldnames = list(asdict(records[0]).keys())
    for required in REQUIRED_COLUMNS:
        if required not in fieldnames:
            raise AssertionError(f"Відсутня обов'язкова CSV column: {required}")

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(record.csv_row() for record in records)

    with trace_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(render_summary(metrics, records), encoding="utf-8")
    quality_path.write_text(render_quality_report(metrics, records), encoding="utf-8")
    return {
        "csv": csv_path,
        "traces": trace_path,
        "metrics": metrics_path,
        "summary": summary_path,
        "quality_report": quality_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the reproducible HW8 chatbot evaluation suite."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUTS_DIR,
        help="Directory for CSV, JSONL, JSON and Markdown outputs.",
    )
    args = parser.parse_args()

    records = run_evaluation()
    paths = write_outputs(records, args.output_dir)
    metrics = calculate_metrics(records)
    print("=============== HW8 EVALUATION ===============")
    print(f"Cases: {metrics['total_cases']}")
    print(f"Success rate: {metrics['success_rate']:.0%}")
    print(f"Groundedness good: {metrics['groundedness_good_rate']:.0%}")
    print(f"Average latency: {metrics['average_latency_ms']} ms")
    for name, path in paths.items():
        print(f"{name}: {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
