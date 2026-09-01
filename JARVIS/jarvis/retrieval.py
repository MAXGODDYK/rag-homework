from __future__ import annotations

import json
import math
import re
from collections import defaultdict

from config.settings import load_settings
from jarvis.config import JarvisConfig
from jarvis.database import Database
from jarvis.ingestion.service import IngestionService
from jarvis.ingestion.vector_index import VectorIndex
from jarvis.models import Citation


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
            query = "SELECT id,project_id,relative_path,display_name FROM documents WHERE user_id=? AND status='ready'"
            parameters: tuple[object, ...] = (user_id,)
        else:
            query = "SELECT id,project_id,relative_path,display_name FROM documents WHERE user_id=? AND project_id IS ? AND status='ready'"
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

            self._reranker = CrossEncoder(self.reranker_model)
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
        eligible_document_ids = {row["id"] for row in documents}
        eligible_chunk_ids = {
            row["id"]
            for row in self.database.query_all(
                "SELECT id FROM chunks WHERE user_id=? AND document_id IN ("
                + ",".join("?" for _ in eligible_document_ids)
                + ")",
                (user_id, *eligible_document_ids),
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
