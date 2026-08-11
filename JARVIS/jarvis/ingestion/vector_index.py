from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

import faiss
import numpy as np


class VectorIndexError(RuntimeError):
    pass


class VectorIndex:
    def __init__(self, root: Path, model_name: str) -> None:
        self.root = root
        self.model_name = model_name
        self._model = None
        self._lock = Lock()

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        with self._lock:
            vectors = self._load_model().encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return np.asarray(vectors, dtype=np.float32)

    def rebuild(self, chunk_ids: list[str], texts: list[str]) -> None:
        if len(chunk_ids) != len(texts):
            raise VectorIndexError("chunk_ids/texts length mismatch")
        self.root.mkdir(parents=True, exist_ok=True)
        vectors = self.encode(texts)
        if vectors.size:
            index = faiss.IndexFlatIP(vectors.shape[1])
            index.add(vectors)
            serialized = faiss.serialize_index(index)
            (self.root / "faiss.index").write_bytes(bytes(serialized))
        else:
            (self.root / "faiss.index").unlink(missing_ok=True)
        np.save(self.root / "embeddings.npy", vectors)
        manifest = {
            "model": self.model_name,
            "dimension": int(vectors.shape[1]) if vectors.ndim == 2 and vectors.size else 0,
            "count": len(chunk_ids),
            "metric": "cosine_via_l2_inner_product",
            "chunk_ids": chunk_ids,
        }
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        manifest_path = self.root / "manifest.json"
        index_path = self.root / "faiss.index"
        if not manifest_path.exists() or not index_path.exists():
            return []
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        serialized = np.frombuffer(index_path.read_bytes(), dtype=np.uint8)
        index = faiss.deserialize_index(serialized)
        if index.ntotal != len(manifest["chunk_ids"]):
            raise VectorIndexError("FAISS/manifest mismatch")
        query_vector = self.encode([query])
        scores, positions = index.search(query_vector, min(top_k, index.ntotal))
        return [
            (manifest["chunk_ids"][int(position)], float(score))
            for score, position in zip(scores[0], positions[0], strict=True)
            if position >= 0
        ]
