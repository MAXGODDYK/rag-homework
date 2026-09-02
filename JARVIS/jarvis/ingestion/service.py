from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pathspec

from config.settings import load_settings
from jarvis.config import JarvisConfig
from jarvis.database import Database
from jarvis.models import new_id, utc_now

from .archives import extract_archive, is_archive
from .chunking import chunk_code, chunk_units
from .chunking_policy import category_for_path, load_chunking_policy
from .parsers import CODE_EXTENSIONS, DocumentParseError, is_blocked_path, is_probably_text, parse_document
from .repository import analyze_code, language_for_path
from .vector_index import VectorIndex
from jarvis.sheets_store import GoogleSheetsChunkStore, GoogleSheetsError


class IngestionError(RuntimeError):
    """Safe ingestion failure."""


EXCLUDED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".idea", ".vscode", ".venv", "venv", "env",
    "node_modules", "dist", "build", "target", "bin", "obj", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", ".nuxt",
})


@dataclass
class SyncSummary:
    """Small, serialisable result of a project scan before retrieval."""

    checked: int = 0
    added: int = 0
    updated: int = 0
    removed: int = 0
    rejected: int = 0
    unchanged: int = 0
    metadata_refreshed: int = 0
    reindexed: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed or self.rejected)

    def public(self) -> dict[str, int]:
        data = asdict(self)
        data.pop("records", None)
        data["changed"] = int(self.changed)
        return data


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


def _project_directory_name(name: str, project_id: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-").lower()
    return f"{cleaned[:80] or 'uploads'}--{(project_id or 'default')[-8:]}"


class IngestionService:
    def __init__(self, config: JarvisConfig, database: Database) -> None:
        self.config = config
        self.database = database
        self.embedding_model = load_settings().embedding_model_name
        self.chunk_store = GoogleSheetsChunkStore(config.project_root)
        self._pending_archives: list[dict[str, Any]] = []

    @property
    def cloud_chunks_enabled(self) -> bool:
        return self.chunk_store.status()["configured"] is True

    def _project_name(self, project_id: str | None) -> str:
        if not project_id:
            return "uploads"
        project = self.database.query_one("SELECT name FROM projects WHERE id=?", (project_id,))
        return str(project["name"]) if project else "project"

    def _legacy_project_root(self, user_id: str, project_id: str | None) -> Path:
        return self.config.state_root / "users" / _safe_component(user_id) / "projects" / _safe_component(project_id or "default")

    def project_state_root(self, user_id: str, project_id: str | None) -> Path:
        """Return a readable project folder and migrate prototype state once."""
        root = self.config.state_root / "projects" / _project_directory_name(self._project_name(project_id), project_id)
        legacy = self._legacy_project_root(user_id, project_id)
        if not root.exists() and legacy.exists():
            root.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy), str(root))
            old_prefix, new_prefix = str(legacy), str(root)
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute("UPDATE documents SET original_path=REPLACE(original_path, ?, ?) WHERE user_id=? AND project_id IS ?", (old_prefix, new_prefix, user_id, project_id))
                    connection.execute("UPDATE document_versions SET extracted_text_path=REPLACE(extracted_text_path, ?, ?) WHERE document_id IN (SELECT id FROM documents WHERE user_id=? AND project_id IS ?)", (old_prefix, new_prefix, user_id, project_id))
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        return root

    _project_root = project_state_root

    def _check_capacity(self, upload_size: int) -> None:
        if upload_size > self.config.max_upload_bytes:
            raise IngestionError("Upload exceeds the configured size limit")
        reserve_root = self.config.state_root.parent if self.config.state_root.parent.exists() else self.config.project_root
        if shutil.disk_usage(reserve_root).free < self.config.minimum_free_disk_bytes:
            raise IngestionError("Ingestion is disabled because the free-disk reserve was reached")

    @staticmethod
    def _directory_size(root: Path) -> int:
        return sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) if root.exists() else 0

    def _check_quotas(self, user_id: str, added: int) -> None:
        projects_root = self.config.state_root / "projects"
        if self._directory_size(projects_root) + added > self.config.max_total_storage_bytes:
            raise IngestionError("Global JARVIS storage quota exceeded")
        row = self.database.query_one("SELECT COALESCE(SUM(size_bytes), 0) AS total FROM documents WHERE user_id=?", (user_id,))
        if int(row["total"] if row else 0) + added > self.config.max_user_storage_bytes:
            raise IngestionError("Per-user storage quota exceeded")

    @staticmethod
    def _metadata(document: dict[str, Any]) -> dict[str, Any]:
        try:
            return json.loads(document.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        temporary.replace(path)

    def _export_current_artifacts(self, user_id: str, project_id: str | None) -> None:
        """Materialise DB current state as inspectable JSONL and manifest artifacts."""
        root = self.project_state_root(user_id, project_id)
        documents = self.database.query_all("SELECT * FROM documents WHERE user_id=? AND project_id IS ? ORDER BY relative_path", (user_id, project_id))
        rows = self.database.query_all("""
            SELECT c.*, d.relative_path, d.sha256 AS source_sha256, d.metadata_json AS document_metadata,
                   d.updated_at AS indexed_at
            FROM chunks c JOIN documents d ON d.id=c.document_id
            WHERE c.user_id=? AND c.project_id IS ? AND d.status='ready'
            ORDER BY d.relative_path, c.ordinal
            """, (user_id, project_id))
        jsonl_rows: list[dict[str, Any]] = []
        chunk_ids: dict[str, list[str]] = {}
        for row in rows:
            document_metadata = self._metadata({"metadata_json": row["document_metadata"]})
            metadata = self._metadata(row)
            chunk_ids.setdefault(row["document_id"], []).append(row["id"])
            jsonl_rows.append({
                "chunk_id": row["id"], "document_id": row["document_id"], "relative_path": row["relative_path"],
                "ordinal": row["ordinal"], "text": row["text"], "metadata": metadata,
                "source_sha256": row["source_sha256"], "source_mtime_ns": document_metadata.get("source_mtime_ns"),
                "indexed_at": document_metadata.get("indexed_at", row["indexed_at"]), "page": row["page"],
                "heading": row["heading"], "sheet": row["sheet"], "cell_range": row["cell_range"],
                "line_start": row["line_start"], "line_end": row["line_end"],
                "representation": row.get("representation", "classic"),
            })
        manifest_files: dict[str, Any] = {}
        for document in documents:
            metadata = self._metadata(document)
            manifest_files[document["relative_path"]] = {
                "relative_path": document["relative_path"], "document_id": document["id"], "sha256": document["sha256"],
                "size_bytes": document["size_bytes"], "source_mtime_ns": metadata.get("source_mtime_ns"),
                "indexed_at": metadata.get("indexed_at", document["updated_at"]), "chunk_ids": chunk_ids.get(document["id"], []),
                "status": document["status"],
            }
        self._write_jsonl(root / "chunks.jsonl", jsonl_rows)
        self._write_json(root / "manifest.json", {
            "schema_version": 1, "project_id": project_id, "project_name": self._project_name(project_id),
            "generated_at": utc_now().isoformat(), "files": manifest_files,
        })

    def _archive_document(self, document: dict[str, Any], *, reason: str) -> None:
        """Keep an audit copy that normal retrieval never reads."""
        if self.cloud_chunks_enabled:
            project_id = str(document.get("project_id") or "")
            chunks = self.database.query_all("SELECT * FROM chunks WHERE document_id=? ORDER BY ordinal", (document["id"],))
            if not chunks and project_id:
                chunks = self.chunk_store.document_chunks(project_id, document["id"])
            source_metadata = self._metadata(document)
            now = utc_now().isoformat()
            for chunk in chunks:
                metadata = self._metadata(chunk)
                self._pending_archives.append({
                    "project_id": project_id, "chunk_id": chunk.get("id", ""), "document_id": document["id"],
                    "relative_path": document["relative_path"], "ordinal": chunk.get("ordinal", 0),
                    "text": chunk.get("text", ""), "metadata_json": json.dumps(metadata, ensure_ascii=False),
                    "source_sha256": document["sha256"], "indexed_at": source_metadata.get("indexed_at", document["updated_at"]),
                    "representation": chunk.get("representation", metadata.get("representation", "classic")),
                    "page": chunk.get("page") or "", "heading": chunk.get("heading") or "", "sheet": chunk.get("sheet") or "",
                    "cell_range": chunk.get("cell_range") or "", "line_start": chunk.get("line_start") or "", "line_end": chunk.get("line_end") or "",
                    "row_version": document["sha256"], "policy_fingerprint": source_metadata.get("chunking_policy", "legacy"), "archived_at": now, "archive_reason": reason,
                })
            return
        root = self.project_state_root(str(document["user_id"]), document.get("project_id")) / "history"
        stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(document["relative_path"]))[:120]
        chunks = self.database.query_all("SELECT * FROM chunks WHERE document_id=? ORDER BY ordinal", (document["id"],))
        source_metadata = self._metadata(document)
        payload = [{
            "chunk_id": chunk["id"], "document_id": document["id"], "relative_path": document["relative_path"],
            "ordinal": chunk["ordinal"], "text": chunk["text"], "metadata": self._metadata(chunk),
            "representation": chunk.get("representation", "classic"),
            "source_sha256": document["sha256"], "source_mtime_ns": source_metadata.get("source_mtime_ns"),
            "archived_at": utc_now().isoformat(),
        } for chunk in chunks]
        archive_name = f"{stamp}--{document['sha256'][:12]}--{stem}"
        self._write_jsonl(root / f"{archive_name}.jsonl", payload)
        self._write_json(root / f"{archive_name}.json", {
            "reason": reason,
            "document": {key: document[key] for key in ("id", "relative_path", "sha256", "status", "original_path")},
            "chunk_count": len(payload),
        })

    def _cloud_file_rows(self, user_id: str, project_id: str | None, revision: str) -> list[dict[str, Any]]:
        rows = self.database.query_all("SELECT * FROM documents WHERE user_id=? AND project_id IS ? ORDER BY relative_path", (user_id, project_id))
        result: list[dict[str, Any]] = []
        for row in rows:
            metadata = self._metadata(row)
            result.append({
                "project_id": project_id or "", "relative_path": row["relative_path"], "document_id": row["id"],
                "sha256": row["sha256"], "size_bytes": row["size_bytes"], "source_mtime_ns": metadata.get("source_mtime_ns", ""),
                "indexed_at": metadata.get("indexed_at", row["updated_at"]), "status": row["status"], "revision": revision,
                "policy_fingerprint": metadata.get("chunking_policy", "legacy"),
            })
        return result

    def _flush_cloud_chunks(self, user_id: str, project_id: str | None) -> None:
        """Upload DB staging chunks, then remove their local text copies."""
        if not self.cloud_chunks_enabled or not project_id:
            return
        try:
            if not self.chunk_store.status()["connected"]:
                self.chunk_store.connect()
            staged = self.database.query_all("SELECT * FROM chunks WHERE user_id=? AND project_id IS ? ORDER BY document_id, ordinal", (user_id, project_id))
            if not staged and not self._pending_archives:
                return
            revision = utc_now().isoformat()
            changed: dict[str, list[dict[str, Any]]] = {}
            for chunk in staged:
                document = self.database.query_one("SELECT * FROM documents WHERE id=?", (chunk["document_id"],))
                if not document:
                    continue
                metadata = self._metadata(document)
                changed.setdefault(chunk["document_id"], []).append({
                    "project_id": project_id, "chunk_id": chunk["id"], "document_id": chunk["document_id"],
                    "relative_path": document["relative_path"], "ordinal": chunk["ordinal"], "representation": chunk.get("representation", "classic"), "text": chunk["text"],
                    "metadata_json": chunk["metadata_json"], "source_sha256": document["sha256"],
                    "indexed_at": metadata.get("indexed_at", document["updated_at"]), "page": chunk["page"] or "",
                    "heading": chunk["heading"] or "", "sheet": chunk["sheet"] or "", "cell_range": chunk["cell_range"] or "",
                    "line_start": chunk["line_start"] or "", "line_end": chunk["line_end"] or "", "row_version": document["sha256"], "policy_fingerprint": metadata.get("chunking_policy", "legacy"),
                })
            row_map = self.chunk_store.write_project_state(
                project_id=project_id, files=self._cloud_file_rows(user_id, project_id, revision),
                changed_documents=changed, archived=self._pending_archives, revision=revision,
            )
            VectorIndex(self.project_state_root(user_id, project_id) / "index", self.embedding_model).set_remote_rows(row_map)
            with self.database.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute("DELETE FROM chunks_fts WHERE user_id=? AND project_id IS ?", (user_id, project_id))
                    connection.execute("DELETE FROM chunks WHERE user_id=? AND project_id IS ?", (user_id, project_id))
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            root = self.project_state_root(user_id, project_id)
            (root / "chunks.jsonl").unlink(missing_ok=True)
            shutil.rmtree(root / "history", ignore_errors=True)
            shutil.rmtree(root / "text", ignore_errors=True)
            self._pending_archives.clear()
        except GoogleSheetsError as error:
            raise IngestionError("Google Sheets is unavailable; no local stale text was used") from error

    def _project_candidates(self, root_path: Path) -> list[Path]:
        gitignore = root_path / ".gitignore"
        spec = pathspec.PathSpec.from_lines("gitwildmatch", gitignore.read_text(encoding="utf-8", errors="replace").splitlines()) if gitignore.exists() else None
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
        return candidates

    def ingest_upload(self, source: Path, *, user_id: str, project_id: str | None, display_name: str | None = None) -> list[dict]:
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
            paths = extract_archive(stored, extracted_root, max_files=self.config.max_archive_files, max_extracted_bytes=self.config.max_extracted_bytes)
            relative_base = extracted_root
        else:
            paths, relative_base = [stored], originals
        records: list[dict] = []
        changed = False
        for path in paths:
            relative = str(path.relative_to(relative_base))
            try:
                record = self._ingest_document(path, user_id, project_id, relative)
            except DocumentParseError as error:
                record = self._mark_rejected(path, user_id, project_id, relative, str(error))
            records.append(record)
            changed = changed or record["status"] in {"ready", "rejected"}
        if changed and not self.cloud_chunks_enabled:
            self.rebuild_vector_index(user_id, project_id)
        if self.cloud_chunks_enabled:
            self._flush_cloud_chunks(user_id, project_id)
            self.rebuild_vector_index(user_id, project_id)
        else:
            self._export_current_artifacts(user_id, project_id)
        return records

    def import_project(self, root_path: Path, *, user_id: str, project_id: str) -> list[dict]:
        resolved = root_path.resolve()
        if not resolved.is_dir():
            raise IngestionError("Project root is not a directory")
        if not self.database.query_one("SELECT id FROM projects WHERE id=? AND user_id=?", (project_id, user_id)):
            raise IngestionError("Project not found")
        self.database.execute("UPDATE projects SET root_path=?, updated_at=? WHERE id=?", (str(resolved), utc_now().isoformat(), project_id))
        return self.sync_project(user_id=user_id, project_id=project_id).records

    def sync_project(self, *, user_id: str, project_id: str | None) -> SyncSummary:
        """Incrementally align a selected repository with current chunks and indexes."""
        summary = SyncSummary()
        if not project_id:
            self._export_current_artifacts(user_id, None)
            return summary
        project = self.database.query_one("SELECT root_path FROM projects WHERE id=? AND user_id=?", (project_id, user_id))
        if not project or not project["root_path"]:
            self._export_current_artifacts(user_id, project_id)
            return summary
        root_path = Path(project["root_path"]).resolve()
        if not root_path.is_dir():
            raise IngestionError("Project folder is unavailable")
        candidates = self._project_candidates(root_path)
        policy_fingerprint = load_chunking_policy().fingerprint
        existing_rows = self.database.query_all("SELECT * FROM documents WHERE user_id=? AND project_id IS ? ORDER BY updated_at DESC", (user_id, project_id))
        existing = {row["relative_path"]: row for row in existing_rows}
        seen: set[str] = set()
        for path in candidates:
            relative = path.relative_to(root_path).as_posix()
            seen.add(relative)
            summary.checked += 1
            row = existing.get(relative)
            stat = path.stat()
            metadata = self._metadata(row) if row else {}
            policy_changed = bool(row and metadata.get("chunking_policy") != policy_fingerprint)
            if row and row["status"] == "ready" and not policy_changed and metadata.get("source_size_bytes") == stat.st_size and metadata.get("source_mtime_ns") == stat.st_mtime_ns:
                summary.unchanged += 1
                continue
            try:
                record = self._ingest_document(path, user_id, project_id, relative, existing=row)
            except DocumentParseError as error:
                record = self._mark_rejected(path, user_id, project_id, relative, str(error), existing=row)
            summary.records.append(record)
            if record["status"] == "ready":
                if record.get("created"):
                    summary.added += 1
                else:
                    summary.updated += 1
                    summary.reindexed += int(policy_changed)
            elif record["status"] == "unchanged":
                summary.unchanged += 1
                summary.metadata_refreshed += int(record.get("metadata_refreshed", False))
            elif record["status"] == "rejected":
                summary.rejected += 1
        for relative, row in existing.items():
            if relative in seen:
                continue
            try:
                Path(row["original_path"]).resolve(strict=False).relative_to(root_path)
            except ValueError:
                continue  # Uploaded files use this project too, but are not repository files.
            self._archive_document(row, reason="source_deleted")
            self._delete_current_document(row["id"])
            summary.removed += 1
            summary.records.append({"document_id": row["id"], "path": relative, "status": "removed"})
        root = self.project_state_root(user_id, project_id)
        if (summary.changed or not (root / "index" / "faiss.index").exists()) and not self.cloud_chunks_enabled:
            self.rebuild_vector_index(user_id, project_id)
        if self.cloud_chunks_enabled:
            self._flush_cloud_chunks(user_id, project_id)
            if summary.changed or not (root / "index" / "faiss.index").exists():
                self.rebuild_vector_index(user_id, project_id)
        else:
            self._export_current_artifacts(user_id, project_id)
        return summary

    def _delete_current_document(self, document_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)", (document_id,))
                connection.execute("DELETE FROM documents WHERE id=?", (document_id,))
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _mark_rejected(self, path: Path, user_id: str, project_id: str | None, relative_path: str, reason: str, *, existing: dict[str, Any] | None = None) -> dict:
        existing = existing or self.database.query_one("SELECT * FROM documents WHERE user_id=? AND project_id IS ? AND relative_path=? ORDER BY updated_at DESC LIMIT 1", (user_id, project_id, relative_path))
        stat, sha, now = path.stat(), _sha256(path), utc_now().isoformat()
        document_id = existing["id"] if existing else new_id("document")
        if existing:
            self._archive_document(existing, reason="parse_rejected")
        metadata = {"source_size_bytes": stat.st_size, "source_mtime_ns": stat.st_mtime_ns, "indexed_at": now, "parse_error": "File could not be indexed"}
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if existing:
                    connection.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)", (document_id,))
                    connection.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
                    connection.execute("DELETE FROM symbols WHERE document_id=?", (document_id,))
                    connection.execute("DELETE FROM graph_edges WHERE source_document_id=?", (document_id,))
                    connection.execute("UPDATE documents SET sha256=?, original_path=?, size_bytes=?, status='rejected', metadata_json=?, updated_at=? WHERE id=?", (sha, str(path), stat.st_size, json.dumps(metadata), now, document_id))
                else:
                    connection.execute("INSERT INTO documents(id,user_id,project_id,display_name,relative_path,media_type,language,sha256,original_path,size_bytes,status,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?, 'rejected',?,?,?)", (document_id, user_id, project_id, path.name, relative_path, "application/octet-stream", language_for_path(path), sha, str(path), stat.st_size, json.dumps(metadata), now, now))
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return {"document_id": document_id, "path": relative_path, "status": "rejected", "reason": "File could not be indexed"}

    def _ingest_document(self, path: Path, user_id: str, project_id: str | None, relative_path: str, *, existing: dict[str, Any] | None = None) -> dict:
        stat, sha, now = path.stat(), _sha256(path), utc_now().isoformat()
        existing = existing or self.database.query_one("SELECT * FROM documents WHERE user_id=? AND project_id IS ? AND relative_path=? ORDER BY updated_at DESC LIMIT 1", (user_id, project_id, relative_path))
        policy = load_chunking_policy()
        category = category_for_path(path)
        if existing and existing["sha256"] == sha and existing["status"] == "ready" and self._metadata(existing).get("chunking_policy") == policy.fingerprint:
            metadata = self._metadata(existing)
            metadata.update({"source_size_bytes": stat.st_size, "source_mtime_ns": stat.st_mtime_ns, "indexed_at": metadata.get("indexed_at", existing["updated_at"])})
            self.database.execute("UPDATE documents SET original_path=?, size_bytes=?, metadata_json=?, updated_at=? WHERE id=?", (str(path), stat.st_size, json.dumps(metadata, ensure_ascii=False), now, existing["id"]))
            return {"document_id": existing["id"], "path": relative_path, "status": "unchanged", "metadata_refreshed": True}
        document_id = existing["id"] if existing else new_id("document")
        if existing:
            self._archive_document(existing, reason="source_changed" if existing["sha256"] != sha else "chunking_policy_changed")
        extracted_dir = self.project_state_root(user_id, project_id) / "text"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        extracted_path = extracted_dir / f"{document_id}_{sha[:12]}.txt"
        chunks = []
        extracted_versions: list[str] = []
        document_metadata: dict[str, Any] = {}
        for representation in policy.representations_for(path):
            # Keep the classic call compatible with the existing parser API;
            # only developer-capable parsers need the explicit variant.
            parsed = parse_document(path) if representation == "classic" else parse_document(path, representation=representation)
            full_text = "\n\n".join(unit.text for unit in parsed.units if unit.text.strip())
            extracted_versions.append(f"[{representation}]\n{full_text}")
            source_form = representation == "developer" and category in {"code", "web_markup", "config_data", "notebooks", "plain_text"}
            if source_form:
                chunks.extend(chunk_code(document_id, full_text, representation=representation))
            else:
                chunks.extend(chunk_units(document_id, parsed.units, representation=representation, normalize_whitespace=representation == "classic"))
            document_metadata.update(parsed.metadata)
        extracted_path.write_text("\n\n".join(extracted_versions), encoding="utf-8")
        analysis_text = next(
            (text.split("\n", 1)[1] for text in extracted_versions if text.startswith("[developer]")),
            extracted_versions[0].split("\n", 1)[-1] if extracted_versions else "",
        )
        is_code = category == "code"
        symbols, edges = analyze_code(path, analysis_text) if is_code else ([], [])
        metadata = dict(document_metadata)
        metadata.update({"source_size_bytes": stat.st_size, "source_mtime_ns": stat.st_mtime_ns, "indexed_at": now, "chunking_policy": policy.fingerprint, "chunking_category": category, "representations": list(policy.representations_for(path))})
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if existing:
                    connection.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)", (document_id,))
                    connection.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
                    connection.execute("DELETE FROM symbols WHERE document_id=?", (document_id,))
                    connection.execute("DELETE FROM graph_edges WHERE source_document_id=?", (document_id,))
                    connection.execute("UPDATE documents SET display_name=?, media_type=?, language=?, sha256=?, original_path=?, size_bytes=?, status='ready', metadata_json=?, updated_at=? WHERE id=?", (path.name, parsed.media_type, language_for_path(path), sha, str(path), stat.st_size, json.dumps(metadata, ensure_ascii=False), now, document_id))
                else:
                    connection.execute("INSERT INTO documents(id,user_id,project_id,display_name,relative_path,media_type,language,sha256,original_path,size_bytes,status,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?, 'ready',?,?,?)", (document_id, user_id, project_id, path.name, relative_path, parsed.media_type, language_for_path(path), sha, str(path), stat.st_size, json.dumps(metadata, ensure_ascii=False), now, now))
                connection.execute("INSERT INTO document_versions(id,document_id,sha256,extracted_text_path,created_at) VALUES(?,?,?,?,?)", (new_id("version"), document_id, sha, str(extracted_path), now))
                for chunk in chunks:
                    representation = str(chunk.metadata.get("representation", "classic"))
                    connection.execute("INSERT INTO chunks(id,document_id,project_id,user_id,ordinal,text,token_estimate,page,heading,sheet,cell_range,line_start,line_end,representation,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (chunk.chunk_id, document_id, project_id, user_id, chunk.ordinal, chunk.text, max(1, len(chunk.text) // 4), chunk.page, chunk.heading, chunk.sheet, chunk.cell_range, chunk.line_start, chunk.line_end, representation, json.dumps(chunk.metadata, ensure_ascii=False)))
                    connection.execute("INSERT INTO chunks_fts(chunk_id,user_id,project_id,text) VALUES(?,?,?,?)", (chunk.chunk_id, user_id, project_id or "", chunk.text))
                for symbol in symbols if project_id else []:
                    connection.execute("INSERT INTO symbols(id,document_id,project_id,name,kind,qualified_name,line_start,line_end,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)", (new_id("symbol"), document_id, project_id, symbol.name, symbol.kind, symbol.qualified_name, symbol.line_start, symbol.line_end, json.dumps(symbol.metadata, ensure_ascii=False)))
                for edge in edges if project_id else []:
                    connection.execute("INSERT INTO graph_edges(id,project_id,source_document_id,target_ref,edge_type,metadata_json) VALUES(?,?,?,?,?,?)", (new_id("edge"), project_id, document_id, edge.target_ref, edge.edge_type, json.dumps(edge.metadata, ensure_ascii=False)))
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return {"document_id": document_id, "path": relative_path, "status": "ready", "created": existing is None, "chunks": len(chunks), "symbols": len(symbols), "edges": len(edges)}

    def rebuild_vector_index(self, user_id: str, project_id: str | None) -> None:
        policy_fingerprint = load_chunking_policy().fingerprint
        if self.cloud_chunks_enabled and project_id:
            try:
                if not self.chunk_store.status()["connected"]:
                    self.chunk_store.connect()
                rows, row_map = self.chunk_store.all_project_chunks(project_id)
            except GoogleSheetsError as error:
                raise IngestionError("Google Sheets is unavailable; vector cache was not rebuilt") from error
            root = self.project_state_root(user_id, project_id) / "index"
            index = VectorIndex(root, self.embedding_model)
            # Keep the basic rebuild signature stable: diagnostic/test
            # adapters may implement the original three-argument method.
            index.rebuild([row["id"] for row in rows], [row["text"] for row in rows], remote_rows=row_map)
            index.set_representations({row["id"]: row.get("representation", "classic") for row in rows})
            index.set_policy_fingerprint(policy_fingerprint)
            return
        rows = self.database.query_all("SELECT c.id,c.text,c.representation FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.user_id=? AND c.project_id IS ? AND d.status='ready' ORDER BY c.document_id,c.ordinal", (user_id, project_id))
        root = self.project_state_root(user_id, project_id) / "index"
        index = VectorIndex(root, self.embedding_model)
        index.rebuild([row["id"] for row in rows], [row["text"] for row in rows])
        index.set_representations({row["id"]: row["representation"] for row in rows})
        index.set_policy_fingerprint(policy_fingerprint)

    def delete_document(self, document_id: str, *, user_id: str) -> None:
        document = self.database.query_one("SELECT * FROM documents WHERE id=? AND user_id=?", (document_id, user_id))
        if document is None:
            raise IngestionError("Document not found")
        project_id = document["project_id"]
        self._archive_document(document, reason="user_deleted")
        versions = self.database.query_all("SELECT extracted_text_path FROM document_versions WHERE document_id=?", (document_id,))
        self._delete_current_document(document_id)
        for version in versions:
            Path(version["extracted_text_path"]).unlink(missing_ok=True)
        original = Path(document["original_path"]).resolve(strict=False)
        try:
            original.relative_to(self.config.state_root.resolve())
        except ValueError:
            pass
        else:
            original.unlink(missing_ok=True)
        if self.cloud_chunks_enabled:
            self._flush_cloud_chunks(user_id, project_id)
        self.rebuild_vector_index(user_id, project_id)
        if not self.cloud_chunks_enabled:
            self._export_current_artifacts(user_id, project_id)
