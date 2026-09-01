from __future__ import annotations

from pathlib import Path

from jarvis.database import Database
from jarvis.models import SessionPolicy, utc_now
from jarvis.rag_service import DesktopRagService
from jarvis.retrieval import DynamicRetriever
from jarvis.sessions import SessionPolicyStore
from helpers import make_config


def seed_scope_database(tmp_path: Path) -> tuple[Database, str]:
    database = Database(tmp_path / "state" / "jarvis.sqlite3")
    database.initialize()
    database.ensure_user("owner", "Owner")
    project = database.create_project("owner", "Study files", None)
    now = utc_now().isoformat()
    for document_id, path, chunk_id in (
        ("doc_a", "selected.md", "chunk_a"),
        ("doc_b", "other.md", "chunk_b"),
    ):
        database.execute(
            "INSERT INTO documents(id,user_id,project_id,display_name,relative_path,media_type,language,sha256,original_path,size_bytes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,'ready',?,?)",
            (document_id, "owner", project["id"], path, path, "text/markdown", "markdown", document_id, str(tmp_path / path), 1, now, now),
        )
        database.execute(
            "INSERT INTO chunks(id,document_id,project_id,user_id,ordinal,text,token_estimate,metadata_json) VALUES(?,?,?,?,?,?,?, '{}')",
            (chunk_id, document_id, project["id"], "owner", 1, f"Evidence from {path}", 5),
        )
    return database, project["id"]


def test_selected_file_is_filtered_before_vector_candidate_cutoff(monkeypatch, tmp_path: Path) -> None:
    database, project_id = seed_scope_database(tmp_path)

    class FakeVectorIndex:
        def __init__(self, *_args: object) -> None: pass
        def count(self) -> int: return 2
        def search(self, _query: str, _top_k: int) -> list[tuple[str, float]]:
            # The unrelated file would win the global top-1 without early filtering.
            return [("chunk_b", 0.99), ("chunk_a", 0.10)]

    monkeypatch.setattr("jarvis.retrieval.VectorIndex", FakeVectorIndex)
    retriever = DynamicRetriever(make_config(tmp_path), database)
    results = retriever.search(
        "semantic only query",
        user_id="owner",
        project_id=project_id,
        source_selector="selected.md",
        top_k=1,
        candidate_k=1,
        rerank=False,
    )

    assert [row["id"] for row in results] == ["chunk_a"]
    assert all(row["relative_path"] == "selected.md" for row in results)


class FakeRetriever:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls: list[dict] = []

    def search(self, _question: str, **kwargs: object) -> list[dict]:
        self.calls.append(kwargs)
        return self.rows


def test_extractive_mode_returns_cited_evidence_without_a_model(tmp_path: Path) -> None:
    database, project_id = seed_scope_database(tmp_path)
    session = database.create_session("owner", project_id, "RAG")
    retriever = FakeRetriever([{
        "id": "chunk_a", "document_id": "doc_a", "display_name": "selected.md", "relative_path": "selected.md",
        "page": None, "heading": "Topic", "sheet": None, "cell_range": None, "line_start": 1, "line_end": 2,
        "text": "Grounded evidence for a direct answer.", "reranker_raw_score": 0.8,
    }])
    policies = SessionPolicyStore()
    policies.set(session["id"], SessionPolicy(provider_profile="extractive", source_selector="selected.md"))
    service = DesktopRagService(database=database, retriever=retriever, policies=policies, providers={})

    answer = service.answer(session["id"], "What is in the selected file?")

    assert answer.grounded is True and answer.fallback is False
    assert answer.provider == "extractive"
    assert [citation.chunk_id for citation in answer.citations] == ["chunk_a"]
    assert retriever.calls == [{"user_id": "owner", "project_id": project_id, "source_selector": "selected.md", "top_k": 3, "candidate_k": 20}]


def test_evidence_gate_blocks_low_relevance_before_provider_call(tmp_path: Path) -> None:
    database, project_id = seed_scope_database(tmp_path)
    session = database.create_session("owner", project_id, "RAG")
    retriever = FakeRetriever([{
        "id": "chunk_a", "document_id": "doc_a", "display_name": "selected.md", "relative_path": "selected.md",
        "page": None, "heading": None, "sheet": None, "cell_range": None, "line_start": None, "line_end": None,
        "text": "Unrelated evidence.", "reranker_raw_score": 0.0001,
    }])
    service = DesktopRagService(database=database, retriever=retriever, policies=SessionPolicyStore(), providers={})

    answer = service.answer(session["id"], "What is the capital of France?")

    assert answer.fallback is True
    assert answer.provider == "evidence-gate"
    assert answer.citations == []
