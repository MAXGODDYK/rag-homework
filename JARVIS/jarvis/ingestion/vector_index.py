from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

import faiss
import numpy as np


class VectorIndexError(RuntimeError):
    pass


class VectorIndex:
    # FlatIP is exact and simple for normal desktop projects.  Above this
    # point an IVF-PQ index keeps its inverted lists in a separate on-disk
    # file and FAISS can page it in with IO_FLAG_MMAP during retrieval.
    MMAP_THRESHOLD = 10_000
    PQ_SUBQUANTIZERS = 48  # 384-dimensional MiniLM vectors divide evenly.
    _models: dict[str, object] = {}
    _models_lock = Lock()

    def __init__(self, root: Path, model_name: str) -> None:
        self.root = root
        self.model_name = model_name
        self._model = None
        self._lock = Lock()

    def _load_model(self):
        if self._model is None:
            with self._models_lock:
                if self.model_name not in self._models:
                    from sentence_transformers import SentenceTransformer

                    self._models[self.model_name] = SentenceTransformer(self.model_name)
                self._model = self._models[self.model_name]
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

    def rebuild(
        self,
        chunk_ids: list[str],
        texts: list[str],
        *,
        remote_rows: dict[str, int] | None = None,
        representations: dict[str, str] | None = None,
        policy_fingerprint: str | None = None,
    ) -> None:
        if len(chunk_ids) != len(texts):
            raise VectorIndexError("chunk_ids/texts length mismatch")
        self.root.mkdir(parents=True, exist_ok=True)
        if os.getenv("JARVIS_LEXICAL_ONLY") == "1":
            (self.root / "faiss.index").unlink(missing_ok=True)
            (self.root / "embeddings.npy").unlink(missing_ok=True)
            (self.root / "ivf_lists.bin").unlink(missing_ok=True)
            (self.root / "manifest.json").write_text(
                json.dumps(
                    {
                        "model": "disabled-in-compact-sidecar",
                        "dimension": 0,
                        "count": 0,
                        "metric": "fts5-only", "index_type": "disabled",
                        "chunk_ids": [],
                        "remote_rows": remote_rows or {},
                        "representations": representations or {},
                        "policy_fingerprint": policy_fingerprint or "legacy",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return
        vectors = self.encode(texts)
        if vectors.size:
            if len(chunk_ids) > self.MMAP_THRESHOLD:
                # The training condition is deliberately conservative: IVF-PQ
                # needs enough samples for 8-bit codebooks.  It is not used by
                # the small course/demo corpora, but prevents a future large
                # import from forcing all inverted lists into RAM.
                nlist = min(1024, max(64, len(chunk_ids) // 40))
                quantizer = faiss.IndexFlatIP(vectors.shape[1])
                index = faiss.IndexIVFPQ(
                    quantizer,
                    vectors.shape[1],
                    nlist,
                    self.PQ_SUBQUANTIZERS,
                    8,
                    faiss.METRIC_INNER_PRODUCT,
                )
                index.train(vectors)
                ivf_path = self.root / "ivf_lists.bin"
                ivf_path.unlink(missing_ok=True)
                index.replace_invlists(
                    faiss.OnDiskInvertedLists(index.nlist, index.code_size, str(ivf_path)),
                    True,
                )
                index.add(vectors)
                index.nprobe = min(16, nlist)
                index_type = "ivfpq_mmap"
            else:
                index = faiss.IndexFlatIP(vectors.shape[1])
                index.add(vectors)
                (self.root / "ivf_lists.bin").unlink(missing_ok=True)
                index_type = "flatip"
            faiss.write_index(index, str(self.root / "faiss.index"))
        else:
            (self.root / "faiss.index").unlink(missing_ok=True)
            (self.root / "ivf_lists.bin").unlink(missing_ok=True)
            index_type = "empty"
        np.save(self.root / "embeddings.npy", vectors)
        manifest = {
            "model": self.model_name,
            "dimension": int(vectors.shape[1]) if vectors.ndim == 2 and vectors.size else 0,
            "count": len(chunk_ids),
            "metric": "cosine_via_l2_inner_product",
            "index_type": index_type,
            "chunk_ids": chunk_ids,
            # The map has IDs and Google Sheet row numbers only, never chunk text.
            "remote_rows": remote_rows or {},
            "representations": representations or {},
            "policy_fingerprint": policy_fingerprint or "legacy",
        }
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def set_remote_rows(self, remote_rows: dict[str, int]) -> None:
        """Attach a Sheets row map without rebuilding embeddings."""
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["remote_rows"] = remote_rows
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_representations(self, representations: dict[str, str]) -> None:
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["representations"] = representations
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_policy_fingerprint(self, policy_fingerprint: str) -> None:
        """Record the chunking policy that produced this text-free cache."""
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["policy_fingerprint"] = policy_fingerprint
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def remote_rows(self) -> dict[str, int]:
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return {}
        try:
            return {
                str(key): int(value)
                for key, value in json.loads(manifest_path.read_text(encoding="utf-8")).get("remote_rows", {}).items()
            }
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def representations(self) -> dict[str, str]:
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return {}
        try:
            return {str(key): str(value) for key, value in json.loads(manifest_path.read_text(encoding="utf-8")).get("representations", {}).items()}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        if os.getenv("JARVIS_LEXICAL_ONLY") == "1":
            return []
        manifest_path = self.root / "manifest.json"
        index_path = self.root / "faiss.index"
        if not manifest_path.exists() or not index_path.exists():
            return []
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        flags = faiss.IO_FLAG_MMAP if manifest.get("index_type") == "ivfpq_mmap" else 0
        index = faiss.read_index(str(index_path), flags)
        try:
            if index.ntotal != len(manifest["chunk_ids"]):
                raise VectorIndexError("FAISS/manifest mismatch")
            query_vector = self.encode([query])
            scores, positions = index.search(query_vector, min(top_k, index.ntotal))
            return [
                (manifest["chunk_ids"][int(position)], float(score))
                for score, position in zip(scores[0], positions[0], strict=True)
                if position >= 0
            ]
        finally:
            # The FAISS object is request-scoped.  For IVF-PQ this releases
            # the memory-mapped handle; for FlatIP it releases the deserialised
            # in-memory index immediately after candidate IDs are produced.
            del index

    def count(self) -> int:
        """Return the indexed vector count without loading an embedding model."""
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            return 0
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            return max(0, int(manifest.get("count", 0)))
        except (OSError, ValueError, json.JSONDecodeError):
            return 0
