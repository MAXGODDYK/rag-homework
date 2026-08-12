from __future__ import annotations

import json
import faiss
from pathlib import Path
from typing import Any
import numpy as np
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"

REQUIRED_FIELDS = {
    "chunk_id",
    "text",
    "document_id",
    "source_file",
    "metadata",
}
MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

INDEX_DIR = PROJECT_ROOT / "index"
EMBEDDINGS_PATH = INDEX_DIR / "embeddings.npy"

INDEX_PATH = INDEX_DIR / "faiss.index"
MANIFEST_PATH = INDEX_DIR / "manifest.json"

def load_chunks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Файл не знайдено: {path}")

    chunks = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Рядок {line_number}: некоректний JSON"
                ) from error
            missing_fields = REQUIRED_FIELDS - chunk.keys()

            if missing_fields:
                raise ValueError(
                    f"Рядок {line_number}: відсутні поля {sorted(missing_fields)}"
                )
            if not isinstance(chunk["text"], str):
                raise ValueError(
                    f"Рядок {line_number}: поле text повинно бути рядком"
                )

            if not chunk["text"].strip():
                raise ValueError(
                    f"Рядок {line_number}: поле text порожнє"
                )
            chunk_id = chunk["chunk_id"]

            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise ValueError(
                    f"Рядок {line_number}: поле chunk_id повинно бути непорожнім рядком"
                )

            if chunk_id in seen_ids:
                raise ValueError(
                    f"Рядок {line_number}: повторний chunk_id {chunk_id}"
                )

            seen_ids.add(chunk_id)
            chunks.append(chunk)

    if not chunks:
        raise ValueError(f"Файл не містить chunks: {path}")

    return chunks

def create_embeddings(
    texts: list[str],
    model: SentenceTransformer,
) -> np.ndarray:
    if not texts:
        raise ValueError("Список текстів для embeddings порожній")
    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    embeddings = embeddings.astype("float32")

    faiss.normalize_L2(embeddings)

    return embeddings

def create_faiss_index(embeddings: np.ndarray) -> faiss.Index:

    if embeddings.ndim != 2:
        raise ValueError(
            f"Embeddings повинні мати 2 виміри, отримано: {embeddings.shape}"
        )

    if embeddings.shape[0] == 0:
        raise ValueError("Матриця embeddings порожня")


    embedding_dimension = embeddings.shape[1]

    index = faiss.IndexFlatIP(embedding_dimension)
    index.add(embeddings)

    return index


def print_section(title: str) -> None:
    """Вивести помітний заголовок розділу."""
    print()
    print(f"=============== {title} ===============")


def main() -> None:
    print_section("ЗАВАНТАЖЕННЯ CHUNKS")
    chunks = load_chunks(CHUNKS_PATH)
    texts = [chunk["text"] for chunk in chunks]

    print(f"Файл: {CHUNKS_PATH}")
    print(f"Завантажено chunks: {len(chunks)}")
    print(f"Унікальних ID: {len({chunk['chunk_id'] for chunk in chunks})}")
    print(f"Перший ID: {chunks[0]['chunk_id']}")
    print(f"Останній ID: {chunks[-1]['chunk_id']}")

    print_section("EMBEDDING MODEL")
    print(f"Embedding model: {MODEL_NAME}")
    print("Завантаження моделі...")

    model = SentenceTransformer(MODEL_NAME)

    print_section("СТВОРЕННЯ EMBEDDINGS")
    print(f"Текстів для embeddings: {len(texts)}")
    print("Створення embeddings...")

    embeddings = create_embeddings(texts, model)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS_PATH, embeddings)

    index = create_faiss_index(embeddings)

    serialized_index = faiss.serialize_index(index)
    INDEX_PATH.write_bytes(serialized_index.tobytes())

    manifest = {
        "model": MODEL_NAME,
        "similarity": "cosine",
        "index_type": "IndexFlatIP",
        "chunk_count": len(chunks),
        "embedding_dimension": int(embeddings.shape[1]),
        "chunks_file": "data/processed/chunks.jsonl",
        "chunk_ids": [chunk["chunk_id"] for chunk in chunks],
    }

    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print_section("РЕЗУЛЬТАТ EMBEDDINGS")
    vector_norms = np.linalg.norm(embeddings, axis=1)

    print(f"Форма embeddings: {embeddings.shape}")
    print(f"Тип даних: {embeddings.dtype}")
    print(f"Мінімальна норма: {vector_norms.min():.6f}")
    print(f"Максимальна норма: {vector_norms.max():.6f}")

    print_section("FAISS INDEX")
    print(f"Тип індексу: {type(index).__name__}")
    print(f"Векторів в індексі: {index.ntotal}")
    print(f"Розмірність індексу: {index.d}")

    print_section("ЗБЕРЕЖЕНІ ФАЙЛИ")
    print(f"Embeddings: {EMBEDDINGS_PATH}")
    print(f"FAISS index: {INDEX_PATH}")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
