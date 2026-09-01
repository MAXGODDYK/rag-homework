from __future__ import annotations

import json

from jarvis.ingestion.vector_index import VectorIndex
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
    index.rebuild(["chunk_1"], ["secret chunk text"], remote_rows={"chunk_1": 42})

    manifest = (tmp_path / "index" / "manifest.json").read_text(encoding="utf-8")

    assert json.loads(manifest)["remote_rows"] == {"chunk_1": 42}
    assert "secret chunk text" not in manifest


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
