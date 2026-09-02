from __future__ import annotations

import json
import math
import re
from collections import defaultdict

from config.settings import load_settings
from jarvis.config import JarvisConfig
from jarvis.database import Database
from jarvis.ingestion.service import IngestionService
from jarvis.ingestion.chunking_policy import load_chunking_policy
from jarvis.ingestion.vector_index import VectorIndex
from jarvis.models import Citation
from jarvis.sheets_store import GoogleSheetsChunkStore, GoogleSheetsError


def _fts_query(question: str) -> str:
    terms = re.findall(r"[\w'’-]{2,}", question.lower(), flags=re.UNICODE)
    return " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:24])


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1 + exponent)


class DynamicRetriever:
    def __init__(self, config: JarvisConfig, database: Database) -> None:
        self.config = config
        self.database = database
        settings = load_settings()
        self.embedding_model = settings.embedding_model_name
        self.reranker_model = settings.reranker_model_name
        self._reranker = None
        self.chunk_store = GoogleSheetsChunkStore(config.project_root)

    def _project_root(self, user_id: str, project_id: str | None):
        return IngestionService(self.config, self.database).project_state_root(user_id, project_id)

    def _eligible_documents(
        self,
        *,
        user_id: str,
        project_id: str | None,
        source_selector: str,
    ) -> list[dict]:
        """Resolve corpus metadata before lexical, vector and reranker scoring.

        The previous prototype filtered explicit files only after the global
        candidate set had already been selected. That could return too few
        results from the selected file and made the file selector misleading.
        """
        if source_selector == "all":
            query = "SELECT id,project_id,relative_path,display_name,metadata_json FROM documents WHERE user_id=? AND status='ready'"
            parameters: tuple[object, ...] = (user_id,)
        else:
            query = "SELECT id,project_id,relative_path,display_name,metadata_json FROM documents WHERE user_id=? AND project_id IS ? AND status='ready'"
            parameters = (user_id, project_id)
        rows = self.database.query_all(query, parameters)
        if source_selector not in {"auto", "all"}:
            expected = source_selector.casefold()
            rows = [
                row
                for row in rows
                if row["relative_path"].casefold() == expected
                or row["display_name"].casefold() == expected
            ]
        return rows

    def _load_reranker(self):
        if self._reranker is None:
            from sentence_transformers import CrossEncoder

            # Qwen3-14B is deliberately kept on the 12 GB GPU through Ollama.
            # BGE-v2-m3 is a large cross-encoder, so running it on the CPU
            # prevents a VRAM collision during one grounded RAG request.
            self._reranker = CrossEncoder(self.reranker_model, device="cpu")
        return self._reranker

    def search(
        self,
        question: str,
        *,
        user_id: str,
        project_id: str | None,
        source_selector: str = "auto",
        top_k: int = 5,
        candidate_k: int = 20,
        rerank: bool = True,
    ) -> list[dict]:
        documents = self._eligible_documents(
            user_id=user_id,
            project_id=project_id,
            source_selector=source_selector,
        )
        if not documents:
            return []
        representation = load_chunking_policy().representation_for_query(
            question, [str(row["relative_path"]) for row in documents]
        )
        available_representations: set[str] = set()
        for document in documents:
            try:
                available_representations.update(json.loads(document.get("metadata_json") or "{}").get("representations", []))
            except (TypeError, json.JSONDecodeError):
                continue
        if representation not in available_representations and available_representations:
            representation = "developer" if "developer" in available_representations else "classic"
        if self.chunk_store.status()["connected"]:
            return self._search_cloud(question, documents, user_id=user_id, source_selector=source_selector, representation=representation, top_k=top_k, candidate_k=candidate_k, rerank=rerank)
        eligible_document_ids = {row["id"] for row in documents}
        eligible_chunk_ids = {
            row["id"]
            for row in self.database.query_all(
                "SELECT id FROM chunks WHERE user_id=? AND representation=? AND document_id IN ("
                + ",".join("?" for _ in eligible_document_ids)
                + ")",
                (user_id, representation, *eligible_document_ids),
            )
        }
        if not eligible_chunk_ids:
            return []

        ranks: dict[str, float] = defaultdict(float)
        fts = _fts_query(question)
        if fts:
            try:
                placeholders = ",".join("?" for _ in eligible_chunk_ids)
                lexical = self.database.query_all(
                    "SELECT chunk_id,bm25(chunks_fts) AS score FROM chunks_fts "
                    "WHERE chunks_fts MATCH ? AND user_id=? AND chunk_id IN ("
                    + placeholders
                    + ") ORDER BY score LIMIT ?",
                    (fts, user_id, *eligible_chunk_ids, candidate_k),
                )
            except Exception:
                lexical = []
            for rank, row in enumerate(lexical, start=1):
                ranks[row["chunk_id"]] += 1 / (60 + rank)

        semantic_projects = list(dict.fromkeys(row["project_id"] for row in documents))
        for semantic_project in semantic_projects:
            vector = VectorIndex(
                self._project_root(user_id, semantic_project) / "index",
                self.embedding_model,
            )
            # Fetch all vectors for this project, then apply the metadata
            # restriction before assigning reciprocal-rank positions.
            semantic_limit = max(candidate_k, vector.count())
            for rank, (chunk_id, _score) in enumerate(
                (item for item in vector.search(question, semantic_limit) if item[0] in eligible_chunk_ids), start=1
            ):
                if rank > candidate_k:
                    break
                ranks[chunk_id] += 1 / (60 + rank)

        terms = re.findall(r"[A-Za-z_$][\w$]{2,}", question)[:20]
        if project_id and terms:
            placeholders = ",".join("?" for _ in terms)
            symbols = self.database.query_all(
                f"SELECT DISTINCT document_id FROM symbols WHERE project_id=? AND document_id IN ({','.join('?' for _ in eligible_document_ids)}) AND lower(name) IN ({placeholders}) LIMIT ?",
                (project_id, *eligible_document_ids, *[term.lower() for term in terms], candidate_k),
            )
            for symbol_rank, symbol in enumerate(symbols, start=1):
                rows = self.database.query_all(
                    "SELECT id FROM chunks WHERE document_id=? AND id IN ("
                    + ",".join("?" for _ in eligible_chunk_ids)
                    + ") ORDER BY ordinal LIMIT 3",
                    (symbol["document_id"], *eligible_chunk_ids),
                )
                for row in rows:
                    ranks[row["id"]] += 0.5 / (60 + symbol_rank)

        candidate_ids = [chunk_id for chunk_id, _ in sorted(ranks.items(), key=lambda item: item[1], reverse=True)[:candidate_k]]
        if not candidate_ids:
            return []
        placeholders = ",".join("?" for _ in candidate_ids)
        scope_clause = "c.user_id=?"
        parameters = (*candidate_ids, user_id)
        rows = self.database.query_all(
            f"SELECT c.*,d.display_name,d.relative_path,d.media_type FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.id IN ({placeholders}) AND {scope_clause}",
            parameters,
        )
        rows = [row for row in rows if row["document_id"] in eligible_document_ids]
        by_id = {row["id"]: row for row in rows}
        ordered = [by_id[chunk_id] for chunk_id in candidate_ids if chunk_id in by_id]
        if rerank and ordered:
            raw_scores = self._load_reranker().predict([(question, row["text"]) for row in ordered])
            for row, raw in zip(ordered, raw_scores, strict=True):
                row["reranker_raw_score"] = float(raw)
                row["reranker_score"] = _sigmoid(float(raw))
            ordered.sort(key=lambda row: row["reranker_raw_score"], reverse=True)
        else:
            for row in ordered:
                row["reranker_raw_score"] = ranks[row["id"]]
                row["reranker_score"] = ranks[row["id"]]
        return ordered[:top_k]

    def _search_cloud(
        self, question: str, documents: list[dict], *, user_id: str, source_selector: str, representation: str, top_k: int, candidate_k: int, rerank: bool
    ) -> list[dict]:
        """Retrieve IDs locally, then fetch only those chunks from Google Sheets."""
        del source_selector
        eligible = {row["id"]: row for row in documents}
        ranked_ids: list[str] = []
        seen: set[str] = set()
        row_maps: dict[str, dict[str, int]] = {}
        for project_id in dict.fromkeys(row["project_id"] for row in documents):
            vector = VectorIndex(self._project_root(user_id, project_id) / "index", self.embedding_model)
            row_maps[str(project_id)] = vector.remote_rows()
            variants = vector.representations()
            chunk_documents = vector.document_ids()
            if len(chunk_documents) != vector.count():
                raise GoogleSheetsError("The local vector cache needs a metadata rebuild")
            eligible_for_project = {
                document_id
                for document_id, document in eligible.items()
                if document.get("project_id") == project_id
            }
            eligible_limit = max(100, candidate_k * 5)
            for chunk_id, _score in vector.search(question, vector.count()):
                if (
                    chunk_documents.get(chunk_id) in eligible_for_project
                    and variants.get(chunk_id, "classic") == representation
                    and chunk_id not in seen
                ):
                    seen.add(chunk_id)
                    ranked_ids.append(chunk_id)
                    if len(ranked_ids) >= eligible_limit:
                        break
        if not ranked_ids:
            return []
        chunks: list[dict] = []
        try:
            for project_id in dict.fromkeys(row["project_id"] for row in documents):
                chunk_rows = self.chunk_store.fetch_chunks(str(project_id), ranked_ids, row_maps.get(str(project_id), {}))
                for row in chunk_rows:
                    document = eligible.get(row["document_id"])
                    if document and row.get("representation", "classic") == representation:
                        row.update({"project_id": project_id, "user_id": user_id, "display_name": document["display_name"], "media_type": ""})
                        chunks.append(row)
        except GoogleSheetsError:
            raise
        by_id = {row["id"]: row for row in chunks}
        ordered = [by_id[chunk_id] for chunk_id in ranked_ids if chunk_id in by_id][:max(100, candidate_k * 5)]
        if not ordered:
            return []
        # BM25 is intentionally restricted to semantic candidates, so full text
        # is neither persisted nor loaded for unrelated chunks.
        terms = re.findall(r"[\w'’-]{2,}", question.casefold())
        document_frequency = defaultdict(int)
        token_sets: dict[str, list[str]] = {}
        for row in ordered:
            tokens = re.findall(r"[\w'’-]{2,}", row["text"].casefold())
            token_sets[row["id"]] = tokens
            for token in set(tokens):
                document_frequency[token] += 1
        average_length = max(1, sum(len(tokens) for tokens in token_sets.values()) / len(token_sets))
        bm25: dict[str, float] = {}
        for row in ordered:
            tokens = token_sets[row["id"]]
            score = 0.0
            for term in terms:
                frequency = tokens.count(term)
                if not frequency:
                    continue
                inverse_frequency = math.log((len(ordered) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5) + 1)
                score += inverse_frequency * frequency * 2.2 / (frequency + 1.2 * (1 - 0.75 + 0.75 * len(tokens) / average_length))
            bm25[row["id"]] = score
        semantic_rank = {row["id"]: position for position, row in enumerate(ordered, start=1)}
        ordered.sort(key=lambda row: (0.75 / (60 + semantic_rank[row["id"]]) + 0.25 * bm25[row["id"]]), reverse=True)
        ordered = ordered[:candidate_k]
        if rerank and ordered:
            raw_scores = self._load_reranker().predict([(question, row["text"]) for row in ordered])
            for row, raw in zip(ordered, raw_scores, strict=True):
                row["reranker_raw_score"] = float(raw)
                row["reranker_score"] = _sigmoid(float(raw))
            ordered.sort(key=lambda row: row["reranker_raw_score"], reverse=True)
        else:
            for row in ordered:
                row["reranker_raw_score"] = bm25[row["id"]]
                row["reranker_score"] = bm25[row["id"]]
        return ordered[:top_k]

    @staticmethod
    def citations(rows: list[dict]) -> list[Citation]:
        return [
            Citation(
                document_id=row["document_id"],
                file_name=row["display_name"],
                source_path=row["relative_path"],
                chunk_id=row["id"],
                page=row["page"],
                heading=row["heading"],
                sheet=row["sheet"],
                cell_range=row["cell_range"],
                line_start=row["line_start"],
                line_end=row["line_end"],
                score=row.get("reranker_score"),
            )
            for row in rows
        ]
