from __future__ import annotations

import json
from pathlib import Path

from jarvis.ingestion.chunking import chunk_code, chunk_units
from jarvis.ingestion.chunking_policy import ChunkingPolicy, category_for_path
from jarvis.ingestion.parsers import parse_document
from jarvis.ingestion.service import IngestionService
from jarvis.ingestion.vector_index import VectorIndex

from helpers import make_config, make_database
from jarvis.sheets_store import (
    CHUNK_HEADERS,
    FILE_HEADERS,
    HISTORY_HEADERS,
    META_HEADERS,
    GoogleSheetsChunkStore,
)


class InMemorySheetsStore(GoogleSheetsChunkStore):
    """Sheets-value mock: tests managed-row behaviour without Google access."""

    def __init__(self) -> None:
        self.tables = {
            "Meta": [META_HEADERS],
            "Files": [FILE_HEADERS],
            "Chunks_Current": [CHUNK_HEADERS],
            "Chunks_History": [HISTORY_HEADERS],
        }

    def ensure_schema(self) -> None:
        return None

    def _values_get(self, cell_range: str) -> list[list[str]]:
        title = cell_range.split("!", 1)[0]
        return [list(map(str, row)) for row in self.tables[title]]

    def _replace_sheet(self, title: str, headers: list[str], rows: list[list[object]]) -> None:
        self.tables[title] = [headers, *[list(row) for row in rows]]

    def _values_append(self, title: str, values: list[list[object]]) -> None:
        self.tables[title].extend([list(row) for row in values])

    def fetch_chunks(self, project_id: str, chunk_ids: list[str], row_map: dict[str, int]) -> list[dict]:
        records = {}
        for number, row in enumerate(self.tables["Chunks_Current"][1:], start=2):
            mapped = self._as_mapping(CHUNK_HEADERS, [str(value) for value in row])
            if mapped["project_id"] == project_id and mapped["chunk_id"] in chunk_ids:
                records[mapped["chunk_id"]] = self._decode_chunk(mapped)
        return [records[chunk_id] for chunk_id in chunk_ids if chunk_id in records]


def test_google_sheets_chunk_decoder_preserves_citation_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_GOOGLE_SERVICE_ACCOUNT_PATH", raising=False)
    store = GoogleSheetsChunkStore(tmp_path)
    row = dict.fromkeys(CHUNK_HEADERS, "")
    row.update({"project_id": "p", "chunk_id": "chunk_1", "document_id": "doc_1", "relative_path": "notes.md", "ordinal": "1", "text": "Only remote text", "metadata_json": json.dumps({"kind": "text"}), "page": "2"})

    decoded = store._decode_chunk(row)

    assert decoded["id"] == "chunk_1"
    assert decoded["text"] == "Only remote text"
    assert decoded["page"] == 2


def test_vector_manifest_keeps_remote_row_map_without_chunk_text(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_LEXICAL_ONLY", "1")
    index = VectorIndex(tmp_path / "index", "unused")
    index.rebuild(
        ["chunk_1"],
        ["secret chunk text"],
        remote_rows={"chunk_1": 42},
        representations={"chunk_1": "developer"},
        policy_fingerprint="policy-test",
    )

    manifest = json.loads((tmp_path / "index" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["remote_rows"] == {"chunk_1": 42}
    assert manifest["representations"] == {"chunk_1": "developer"}
    assert manifest["policy_fingerprint"] == "policy-test"
    assert index.remote_rows() == {"chunk_1": 42}
    assert "secret chunk text" not in json.dumps(manifest)


def test_managed_rows_replace_changed_document_and_archive_old_chunks() -> None:
    store = InMemorySheetsStore()
    old = {key: "" for key in CHUNK_HEADERS}
    old.update({"project_id": "project", "chunk_id": "old", "document_id": "document", "relative_path": "notes.md", "ordinal": "1", "text": "old text", "metadata_json": "{}"})
    store.tables["Chunks_Current"].append([old[key] for key in CHUNK_HEADERS])
    new = {key: "" for key in CHUNK_HEADERS}
    new.update({"project_id": "project", "chunk_id": "new", "document_id": "document", "relative_path": "notes.md", "ordinal": "1", "text": "new text", "metadata_json": "{}", "source_sha256": "new-sha"})
    archived = dict(old)
    archived.update({"archived_at": "2026-09-02T00:00:00Z", "archive_reason": "source_changed"})

    row_map = store.write_project_state(
        project_id="project",
        files=[],
        changed_documents={"document": [new]},
        archived=[archived],
        revision="revision-2",
    )

    assert row_map == {"new": 2}
    assert [row[1] for row in store.tables["Chunks_Current"][1:]] == ["new"]
    assert [row[1] for row in store.tables["Chunks_History"][1:]] == ["old"]
    assert store.tables["Meta"][1] == ["project:project:revision", "revision-2"]


def test_html_classic_is_clean_but_developer_preserves_source(tmp_path) -> None:
    path = tmp_path / "page.html"
    path.write_text("<html><head><meta name='x'><style>.a{color:red}</style></head><body><h1>Title</h1><script>alert(1)</script><p>Hello</p></body></html>", encoding="utf-8")

    classic = parse_document(path)
    developer = parse_document(path, representation="developer")
    classic_text = "\n".join(unit.text for unit in classic.units)
    developer_chunks = chunk_code("doc", developer.units[0].text, representation="developer")

    assert "<meta" not in classic_text and "alert(1)" not in classic_text
    assert "<meta" in developer_chunks[0].text and "<script>" in developer_chunks[0].text
    assert developer_chunks[0].line_start == 1


def test_policy_keeps_code_as_developer_and_routes_mixed_questions() -> None:
    policy = ChunkingPolicy(global_mode="mixed")

    assert category_for_path(Path("main.py")) == "code"
    assert policy.representations_for(Path("main.py")) == ("developer",)
    assert policy.representations_for(Path("page.html")) == ("classic", "developer")
    assert policy.representation_for_query("Why does this CSS selector fail?", ["page.html"]) == "developer"
    assert policy.representation_for_query("Summarize the web page", ["page.html"]) == "classic"


def test_representations_produce_distinct_chunk_ids() -> None:
    from jarvis.ingestion.models import ExtractedUnit

    unit = ExtractedUnit(text="A long paragraph about JARVIS.")
    classic = chunk_units("doc", [unit], representation="classic")
    developer = chunk_units("doc", [unit], representation="developer", normalize_whitespace=False)

    assert classic[0].chunk_id != developer[0].chunk_id
    assert classic[0].metadata["representation"] == "classic"
    assert developer[0].metadata["representation"] == "developer"


def test_chunking_policy_change_reindexes_project_on_next_sync(monkeypatch, tmp_path) -> None:
    config = make_config(tmp_path)
    database = make_database(config)
    root = tmp_path / "web-project"
    root.mkdir()
    page = root / "page.html"
    page.write_text("<html><body><h1>Topic</h1><script>const internal = 1</script></body></html>", encoding="utf-8")
    project = database.create_project("owner", "Web", str(root))
    service = IngestionService(config, database)
    monkeypatch.setattr(VectorIndex, "rebuild", lambda self, ids, texts: None)

    first = service.sync_project(user_id="owner", project_id=project["id"])
    monkeypatch.setenv("JARVIS_CHUNKING_WEB_MARKUP", "mixed")
    second = service.sync_project(user_id="owner", project_id=project["id"])
    representations = {row["representation"] for row in database.query_all("SELECT representation FROM chunks WHERE project_id=?", (project["id"],))}

    assert first.added == 1
    assert second.updated == 1 and second.reindexed == 1
    assert representations == {"classic", "developer"}
