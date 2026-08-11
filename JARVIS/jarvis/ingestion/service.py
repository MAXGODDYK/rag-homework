from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import pathspec

from config.settings import load_settings
from jarvis.config import JarvisConfig
from jarvis.database import Database
from jarvis.models import new_id, utc_now

from .archives import extract_archive, is_archive
from .chunking import chunk_code, chunk_units
from .models import ParsedDocument
from .parsers import CODE_EXTENSIONS, DocumentParseError, is_blocked_path, is_probably_text, parse_document
from .repository import analyze_code, language_for_path
from .vector_index import VectorIndex


class IngestionError(RuntimeError):
    """Safe ingestion failure."""


EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git", ".hg", ".svn", ".idea", ".vscode", ".venv", "venv", "env",
        "node_modules", "dist", "build", "target", "bin", "obj", "__pycache__",
        ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", ".nuxt",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_component(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(name).name).strip(" .")
    return cleaned[:180] or "upload"


class IngestionService:
    def __init__(self, config: JarvisConfig, database: Database) -> None:
        self.config = config
        self.database = database
        self.embedding_model = load_settings().embedding_model_name

    def project_state_root(self, user_id: str, project_id: str | None) -> Path:
        return self.config.state_root / "users" / _safe_component(user_id) / "projects" / _safe_component(project_id or "default")

    # Compatibility for the first prototype; new callers use the public method.
    _project_root = project_state_root

    def _check_capacity(self, upload_size: int) -> None:
        if upload_size > self.config.max_upload_bytes:
            raise IngestionError("Upload exceeds the configured size limit")
        free = shutil.disk_usage(self.config.state_root.parent if self.config.state_root.parent.exists() else self.config.project_root).free
        if free < self.config.minimum_free_disk_bytes:
            raise IngestionError("Ingestion is disabled because the free-disk reserve was reached")

    def _directory_size(self, root: Path) -> int:
        return sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) if root.exists() else 0

    def _check_quotas(self, user_id: str, added: int) -> None:
        user_root = self.config.state_root / "users" / _safe_component(user_id)
        if self._directory_size(user_root) + added > self.config.max_user_storage_bytes:
            raise IngestionError("Per-user storage quota exceeded")
        if self._directory_size(self.config.state_root / "users") + added > self.config.max_total_storage_bytes:
            raise IngestionError("Global JARVIS storage quota exceeded")

    def ingest_upload(
        self,
        source: Path,
        *,
        user_id: str,
        project_id: str | None,
        display_name: str | None = None,
    ) -> list[dict]:
        source = source.resolve()
        if not source.is_file():
            raise IngestionError("Upload source is not a file")
        self._check_capacity(source.stat().st_size)
        self._check_quotas(user_id, source.stat().st_size)
        root = self.project_state_root(user_id, project_id)
        originals = root / "originals"
        originals.mkdir(parents=True, exist_ok=True)
        stored = originals / f"{new_id('upload')}_{_safe_name(display_name or source.name)}"
        shutil.copy2(source, stored)

        if is_archive(stored):
            extracted_root = root / "extracted" / new_id("archive")
            paths = extract_archive(
                stored,
                extracted_root,
                max_files=self.config.max_archive_files,
                max_extracted_bytes=self.config.max_extracted_bytes,
            )
            relative_base = extracted_root
        else:
            paths = [stored]
            relative_base = originals

        records: list[dict] = []
        for path in paths:
            try:
                relative = str(path.relative_to(relative_base))
                records.append(
                    self._ingest_document(path, user_id, project_id, relative)
                )
            except DocumentParseError as error:
                records.append({"path": str(path), "status": "rejected", "reason": str(error)})
        self.rebuild_vector_index(user_id, project_id)
        return records

    def import_project(self, root_path: Path, *, user_id: str, project_id: str) -> list[dict]:
        root_path = root_path.resolve()
        if not root_path.is_dir():
            raise IngestionError("Project root is not a directory")
        gitignore = root_path / ".gitignore"
        spec = None
        if gitignore.exists():
            spec = pathspec.PathSpec.from_lines("gitwildmatch", gitignore.read_text(encoding="utf-8", errors="replace").splitlines())
        candidates: list[Path] = []
        total = 0
        for path in root_path.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root_path)
            if any(part.lower() in EXCLUDED_DIRECTORIES for part in relative.parts):
                continue
            if spec and spec.match_file(relative.as_posix()):
                continue
            if is_blocked_path(path) or not is_probably_text(path):
                continue
            total += path.stat().st_size
            if total > self.config.max_extracted_bytes or len(candidates) >= self.config.max_archive_files:
                raise IngestionError("Project exceeds configured indexing limits")
            candidates.append(path)
        self._check_quotas(user_id, total)
        records = [
            self._ingest_document(path, user_id, project_id, str(path.relative_to(root_path)))
            for path in candidates
        ]
        self.rebuild_vector_index(user_id, project_id)
        return records

    def _ingest_document(self, path: Path, user_id: str, project_id: str | None, relative_path: str) -> dict:
        parsed = parse_document(path)
        sha = _sha256(path)
        now = utc_now().isoformat()
        existing = self.database.query_one(
            "SELECT * FROM documents WHERE user_id=? AND project_id IS ? AND relative_path=? ORDER BY updated_at DESC LIMIT 1",
            (user_id, project_id, relative_path),
        )
        if existing and existing["sha256"] == sha and existing["status"] == "ready":
            return {"document_id": existing["id"], "path": relative_path, "status": "unchanged"}
        document_id = existing["id"] if existing else new_id("document")
        extracted_dir = self.project_state_root(user_id, project_id) / "text"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        extracted_path = extracted_dir / f"{document_id}_{sha[:12]}.txt"
        full_text = "\n\n".join(unit.text for unit in parsed.units if unit.text.strip())
        extracted_path.write_text(full_text, encoding="utf-8")
        is_code = path.suffix.lower() in CODE_EXTENSIONS or parsed.metadata.get("kind") == "code"
        chunks = chunk_code(document_id, full_text) if is_code else chunk_units(document_id, parsed.units)
        symbols, edges = analyze_code(path, full_text) if is_code else ([], [])

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if existing:
                    connection.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)", (document_id,))
                    connection.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
                    connection.execute("DELETE FROM symbols WHERE document_id=?", (document_id,))
                    connection.execute("DELETE FROM graph_edges WHERE source_document_id=?", (document_id,))
                    connection.execute(
                        "UPDATE documents SET display_name=?, media_type=?, language=?, sha256=?, original_path=?, size_bytes=?, status='ready', metadata_json=?, updated_at=? WHERE id=?",
                        (
                            path.name, parsed.media_type, language_for_path(path), sha, str(path), path.stat().st_size,
                            json.dumps(parsed.metadata, ensure_ascii=False), now, document_id,
                        ),
                    )
                else:
                    connection.execute(
                        "INSERT INTO documents(id,user_id,project_id,display_name,relative_path,media_type,language,sha256,original_path,size_bytes,status,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?, 'ready',?,?,?)",
                        (
                            document_id, user_id, project_id, path.name, relative_path, parsed.media_type,
                            language_for_path(path), sha, str(path), path.stat().st_size,
                            json.dumps(parsed.metadata, ensure_ascii=False), now, now,
                        ),
                    )
                connection.execute(
                    "INSERT INTO document_versions(id,document_id,sha256,extracted_text_path,created_at) VALUES(?,?,?,?,?)",
                    (new_id("version"), document_id, sha, str(extracted_path), now),
                )
                for chunk in chunks:
                    connection.execute(
                        "INSERT INTO chunks(id,document_id,project_id,user_id,ordinal,text,token_estimate,page,heading,sheet,cell_range,line_start,line_end,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            chunk.chunk_id, document_id, project_id, user_id, chunk.ordinal, chunk.text,
                            max(1, len(chunk.text) // 4), chunk.page, chunk.heading, chunk.sheet,
                            chunk.cell_range, chunk.line_start, chunk.line_end,
                            json.dumps(chunk.metadata, ensure_ascii=False),
                        ),
                    )
                    connection.execute(
                        "INSERT INTO chunks_fts(chunk_id,user_id,project_id,text) VALUES(?,?,?,?)",
                        (chunk.chunk_id, user_id, project_id or "", chunk.text),
                    )
                for symbol in symbols if project_id else []:
                    connection.execute(
                        "INSERT INTO symbols(id,document_id,project_id,name,kind,qualified_name,line_start,line_end,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            new_id("symbol"), document_id, project_id, symbol.name, symbol.kind,
                            symbol.qualified_name, symbol.line_start, symbol.line_end,
                            json.dumps(symbol.metadata, ensure_ascii=False),
                        ),
                    )
                for edge in edges if project_id else []:
                    connection.execute(
                        "INSERT INTO graph_edges(id,project_id,source_document_id,target_ref,edge_type,metadata_json) VALUES(?,?,?,?,?,?)",
                        (
                            new_id("edge"), project_id, document_id, edge.target_ref, edge.edge_type,
                            json.dumps(edge.metadata, ensure_ascii=False),
                        ),
                    )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return {
            "document_id": document_id,
            "path": relative_path,
            "status": "ready",
            "chunks": len(chunks),
            "symbols": len(symbols),
            "edges": len(edges),
        }

    def rebuild_vector_index(self, user_id: str, project_id: str | None) -> None:
        rows = self.database.query_all(
            "SELECT id,text FROM chunks WHERE user_id=? AND project_id IS ? ORDER BY document_id,ordinal",
            (user_id, project_id),
        )
        root = self.project_state_root(user_id, project_id) / "index"
        VectorIndex(root, self.embedding_model).rebuild(
            [row["id"] for row in rows], [row["text"] for row in rows]
        )

    def delete_document(self, document_id: str, *, user_id: str) -> None:
        document = self.database.query_one(
            "SELECT * FROM documents WHERE id=? AND user_id=?", (document_id, user_id)
        )
        if document is None:
            raise IngestionError("Document not found")
        project_id = document["project_id"]
        versions = self.database.query_all(
            "SELECT extracted_text_path FROM document_versions WHERE document_id=?",
            (document_id,),
        )
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)",
                    (document_id,),
                )
                connection.execute("DELETE FROM documents WHERE id=?", (document_id,))
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        for version in versions:
            Path(version["extracted_text_path"]).unlink(missing_ok=True)
        self.rebuild_vector_index(user_id, project_id)
