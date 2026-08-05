from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import load_settings
from scripts.rag.schemas import format_rag_answer
from scripts.rag.service import RagAnswerService


def print_section(title: str) -> None:
    print()
    print(f"=============== {title} ===============")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grounded RAG answer generation for HW4"
    )
    parser.add_argument("question", help="Питання користувача")
    parser.add_argument(
        "--provider",
        choices=("openai", "freemodel", "local"),
        default="openai",
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--source-file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    service = RagAnswerService(settings=settings)

    print_section("HW4 GROUNDED RAG")
    print(f"Provider: {args.provider}")
    print(f"Top-k: {args.top_k}")
    print(f"Candidate-k: {args.candidate_k}")

    try:
        result = service.answer(
            question=args.question,
            provider_name=args.provider,
            top_k=args.top_k,
            candidate_k=args.candidate_k,
            source_file=args.source_file,
        )
    except Exception as error:
        print_section("ПОМИЛКА")
        print(str(error))
        raise SystemExit(1) from error

    print_section("ВІДПОВІДЬ")
    print(format_rag_answer(result))

    print_section("RETRIEVED CHUNKS")
    for rank, chunk in enumerate(result.retrieved_chunks, start=1):
        preview = " ".join(chunk["text"].split())
        if len(preview) > 220:
            preview = preview[:219].rstrip() + "…"
        print(
            f"Top-{rank}: {chunk['chunk_id']} | "
            f"raw={chunk['reranker_raw_score']:.4f}"
        )
        print(f"Source: {chunk['source_file']}")
        print(f"Section: {chunk['section']}")
        print(f"Text: {preview}")


if __name__ == "__main__":
    main()
