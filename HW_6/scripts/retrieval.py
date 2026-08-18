from __future__ import annotations

import json
import argparse
from pathlib import Path
from typing import Any

import faiss
import numpy as np

try:
    from .build_index import load_chunks
except ImportError:
    from build_index import load_chunks
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"
INDEX_PATH = PROJECT_ROOT / "index" / "faiss.index"
MANIFEST_PATH = PROJECT_ROOT / "index" / "manifest.json"

def print_section(title: str) -> None:
    print()
    print(f"=============== {title} ===============")

def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Manifest не знайдено: {path}")

    try:
        manifest = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Manifest містить некоректний JSON: {path}"
        ) from error

    required_fields = {
        "model",
        "similarity",
        "index_type",
        "chunk_count",
        "embedding_dimension",
        "chunk_ids",
    }

    missing_fields = required_fields - manifest.keys()

    if missing_fields:
        raise ValueError(
            f"У manifest відсутні поля: {sorted(missing_fields)}"
        )

    return manifest

def load_faiss_index(path: Path) -> faiss.Index:
    if not path.exists():
        raise FileNotFoundError(f"FAISS index не знайдено: {path}")

    serialized_index = np.frombuffer(
        path.read_bytes(),
        dtype="uint8",
    )

    return faiss.deserialize_index(serialized_index)

def validate_artifacts(
    chunks: list[dict[str, Any]],
    manifest: dict[str, Any],
    index: faiss.Index,
) -> None:
    current_chunk_ids = [chunk["chunk_id"] for chunk in chunks]

    if manifest["chunk_ids"] != current_chunk_ids:
        raise ValueError(
            "Порядок chunk_id у manifest не відповідає chunks.jsonl"
        )

    if manifest["chunk_count"] != len(chunks):
        raise ValueError(
            "Кількість chunks у manifest не відповідає chunks.jsonl"
        )

    if index.ntotal != len(chunks):
        raise ValueError(
            "Кількість векторів FAISS не відповідає chunks.jsonl"
        )

    if index.d != manifest["embedding_dimension"]:
        raise ValueError(
            "Розмірність FAISS не відповідає manifest"
        )

def semantic_search(
    query: str,
    top_k: int,
    model: SentenceTransformer,
    index: faiss.Index,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    query = query.strip()

    if not query:
        raise ValueError("Query не може бути порожнім")

    if top_k < 1:
        raise ValueError("top-k повинен бути не менше 1")

    top_k = min(top_k, len(chunks))

    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
    )

    query_embedding = query_embedding.astype("float32")
    faiss.normalize_L2(query_embedding)

    scores, positions = index.search(
        query_embedding,
        top_k,
    )

    results = []

    for score, position in zip(scores[0], positions[0]):
        if position == -1:
            continue

        chunk = chunks[int(position)]

        results.append(
            {
                "chunk_id": chunk["chunk_id"],
                "score": float(score),
                "document_id": chunk["document_id"],
                "source_file": chunk["source_file"],
                "text": chunk["text"],
                "metadata": chunk["metadata"],
            }
        )

    return results

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Semantic retrieval для knowledge base"
    )

    parser.add_argument(
        "query",
        help="Питання користувача",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Кількість результатів",
    )

    return parser.parse_args()

def main() -> None:
    print_section("ЗАВАНТАЖЕННЯ RETRIEVAL")

    args = parse_args()

    chunks = load_chunks(CHUNKS_PATH)
    manifest = load_manifest(MANIFEST_PATH)
    index = load_faiss_index(INDEX_PATH)

    validate_artifacts(chunks, manifest, index)

    print(f"Chunks: {len(chunks)}")
    print(f"Модель: {manifest['model']}")
    print(f"Тип індексу: {type(index).__name__}")
    print(f"Векторів: {index.ntotal}")
    print(f"Розмірність: {index.d}")
    print("Перевірка артефактів: OK")

    print_section("ЗАВАНТАЖЕННЯ МОДЕЛІ")
    print(f"Модель: {manifest['model']}")

    model = SentenceTransformer(manifest["model"])

    results = semantic_search(
        query=args.query,
        top_k=args.top_k,
        model=model,
        index=index,
        chunks=chunks,
    )

    print_section("РЕЗУЛЬТАТИ ПОШУКУ")
    print(f"Query: {args.query}")
    print(f"Знайдено: {len(results)}")

    for rank, result in enumerate(results, start=1):
        metadata = result["metadata"]
        preview = " ".join(result["text"].split())

        if len(preview) > 300:
            preview = preview[:299].rstrip() + "…"

        print()
        print(f"Top-{rank}")
        print(f"Chunk ID: {result['chunk_id']}")
        print(f"Score: {result['score']:.4f}")
        print(f"Document: {result['document_id']}")
        print(f"Source: {result['source_file']}")
        print(f"Title: {metadata.get('title', '—')}")
        print(f"Section: {metadata.get('section', '—')}")
        print(f"Text: {preview}")

if __name__ == "__main__":
    main()
