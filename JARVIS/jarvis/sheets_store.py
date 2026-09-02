from __future__ import annotations

"""Google Sheets backed source-of-truth for JARVIS chunk text.

The local vector cache deliberately contains IDs and embeddings only.  This
module is the only component allowed to persist or return chunk text once the
Google backend is connected.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from config.settings import PROJECT_ROOT, _load_local_constants


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_API = "https://www.googleapis.com/drive/v3/files"

META_HEADERS = ["key", "value"]
FILE_HEADERS = ["project_id", "relative_path", "document_id", "sha256", "size_bytes", "source_mtime_ns", "indexed_at", "status", "revision", "policy_fingerprint"]
CHUNK_HEADERS = ["project_id", "chunk_id", "document_id", "relative_path", "ordinal", "representation", "text", "metadata_json", "source_sha256", "indexed_at", "page", "heading", "sheet", "cell_range", "line_start", "line_end", "row_version", "policy_fingerprint"]
HISTORY_HEADERS = CHUNK_HEADERS + ["archived_at", "archive_reason"]
LEGACY_FILE_HEADERS = FILE_HEADERS[:-1]
LEGACY_CHUNK_HEADERS = [header for header in CHUNK_HEADERS if header not in {"representation", "policy_fingerprint"}]
LEGACY_HISTORY_HEADERS = LEGACY_CHUNK_HEADERS + ["archived_at", "archive_reason"]


class GoogleSheetsError(RuntimeError):
    """Safe error for unavailable or invalid Google Sheets storage."""


@dataclass(frozen=True)
class GoogleSheetsSettings:
    service_account_path: Path | None
    spreadsheet_id: str
    owner_email: str

    @classmethod
    def load(cls) -> "GoogleSheetsSettings":
        # The desktop settings screen writes .env, while an advanced local
        # setup may use the ignored constants.py.  Keep the same precedence as
        # the rest of JARVIS: process environment, then private constants.
        constants = _load_local_constants(PROJECT_ROOT / "local_config" / "constants.py")

        def value(name: str) -> str:
            environment_value = os.getenv(name)
            if environment_value is not None:
                return environment_value.strip()
            return str(getattr(constants, name, "") or "").strip()

        raw_path = value("JARVIS_GOOGLE_SERVICE_ACCOUNT_PATH")
        return cls(
            service_account_path=Path(raw_path).expanduser().resolve() if raw_path else None,
            spreadsheet_id=value("JARVIS_GOOGLE_SPREADSHEET_ID"),
            owner_email=value("JARVIS_GOOGLE_OWNER_EMAIL"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.service_account_path and self.service_account_path.is_file() and self.owner_email)


class GoogleSheetsChunkStore:
    """Small REST client; no Google credentials or text are logged."""

    def __init__(self, project_root: Path, client: httpx.Client | None = None) -> None:
        self.project_root = project_root
        self._client = client or httpx.Client(timeout=30)
        self._token: str | None = None

    @property
    def settings(self) -> GoogleSheetsSettings:
        return GoogleSheetsSettings.load()

    def status(self) -> dict[str, object]:
        settings = self.settings
        return {
            "configured": settings.configured,
            "connected": bool(settings.configured and settings.spreadsheet_id),
            "spreadsheet_id": settings.spreadsheet_id or None,
            "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{settings.spreadsheet_id}" if settings.spreadsheet_id else None,
        }

    def _access_token(self) -> str:
        if self._token:
            return self._token
        settings = self.settings
        if not settings.configured or not settings.service_account_path:
            raise GoogleSheetsError("Google Sheets is not configured")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.service_account import Credentials

            credentials = Credentials.from_service_account_file(
                str(settings.service_account_path), scopes=[SHEETS_SCOPE, DRIVE_FILE_SCOPE]
            )
            credentials.refresh(Request())
        except Exception as error:  # Credential details must not leave the desktop.
            raise GoogleSheetsError("Google service account could not be authorised") from error
        self._token = str(credentials.token)
        return self._token

    def _request(self, method: str, url: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.request(
                method, url, json=payload,
                headers={"Authorization": f"Bearer {self._access_token()}"},
            )
        except httpx.HTTPError as error:
            raise GoogleSheetsError("Google Sheets is unavailable") from error
        if response.status_code >= 400:
            raise GoogleSheetsError("Google Sheets rejected the request")
        try:
            return response.json()
        except ValueError as error:
            raise GoogleSheetsError("Google Sheets returned an invalid response") from error

    @staticmethod
    def _range(sheet: str) -> str:
        return sheet.replace(" ", "_")

    def connect(self) -> dict[str, object]:
        """Create and share a managed spreadsheet once; otherwise validate it."""
        settings = self.settings
        if not settings.configured:
            raise GoogleSheetsError("Set the service account JSON path and Google owner e-mail first")
        if settings.spreadsheet_id:
            self.ensure_schema()
            return self.status()
        payload = {
            "properties": {"title": "JARVIS DB"},
            "sheets": [{"properties": {"title": title}} for title in ("Meta", "Files", "Chunks_Current", "Chunks_History")],
        }
        created = self._request("POST", SHEETS_API, payload=payload)
        spreadsheet_id = str(created["spreadsheetId"])
        self._request("POST", f"{DRIVE_API}/{spreadsheet_id}/permissions?sendNotificationEmail=true", payload={
            "type": "user", "role": "writer", "emailAddress": settings.owner_email,
        })
        self._save_spreadsheet_id(spreadsheet_id)
        self.ensure_schema()
        return self.status()

    def _save_spreadsheet_id(self, spreadsheet_id: str) -> None:
        path = self.project_root / ".env"
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        lines = [line for line in old.splitlines() if not line.startswith("JARVIS_GOOGLE_SPREADSHEET_ID=")]
        lines.append(f"JARVIS_GOOGLE_SPREADSHEET_ID={json.dumps(spreadsheet_id)}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.environ["JARVIS_GOOGLE_SPREADSHEET_ID"] = spreadsheet_id

    def _sheet_id_by_title(self) -> dict[str, int]:
        data = self._request("GET", f"{SHEETS_API}/{self._spreadsheet_id()}")
        return {item["properties"]["title"]: int(item["properties"]["sheetId"]) for item in data.get("sheets", [])}

    def _spreadsheet_id(self) -> str:
        value = self.settings.spreadsheet_id
        if not value:
            raise GoogleSheetsError("Google Sheets database has not been created")
        return value

    def ensure_schema(self) -> None:
        identifiers = self._sheet_id_by_title()
        required = {"Meta": META_HEADERS, "Files": FILE_HEADERS, "Chunks_Current": CHUNK_HEADERS, "Chunks_History": HISTORY_HEADERS}
        missing = [title for title in required if title not in identifiers]
        if missing:
            self._request("POST", f"{SHEETS_API}/{self._spreadsheet_id()}:batchUpdate", payload={
                "requests": [{"addSheet": {"properties": {"title": title}}} for title in missing]
            })
        for title, headers in required.items():
            current = self._values_get(f"{title}!1:1")
            legacy_headers = LEGACY_FILE_HEADERS if title == "Files" else (LEGACY_CHUNK_HEADERS if title == "Chunks_Current" else (LEGACY_HISTORY_HEADERS if title == "Chunks_History" else []))
            if current and current[0] == legacy_headers:
                self._migrate_legacy_sheet(title, legacy_headers, headers)
            elif current and current[0] not in (headers, []):
                raise GoogleSheetsError("Google Sheets schema was changed outside JARVIS")
            if not current:
                self._values_update(f"{title}!A1", [headers])

    def _migrate_legacy_sheet(self, title: str, old_headers: list[str], headers: list[str]) -> None:
        """One-way schema migration without losing existing cloud chunks."""
        rows = [self._as_mapping(old_headers, row) for row in self._values_get(title)[1:]]
        for row in rows:
            row.setdefault("representation", "classic")
            row.setdefault("policy_fingerprint", "legacy")
        self._replace_sheet(title, headers, [[row.get(header, "") for header in headers] for row in rows])

    def _values_get(self, cell_range: str) -> list[list[str]]:
        data = self._request("GET", f"{SHEETS_API}/{self._spreadsheet_id()}/values/{cell_range}")
        return [[str(value) for value in row] for row in data.get("values", [])]

    def _values_update(self, cell_range: str, values: list[list[Any]]) -> None:
        self._request("PUT", f"{SHEETS_API}/{self._spreadsheet_id()}/values/{cell_range}?valueInputOption=RAW", payload={"range": cell_range, "majorDimension": "ROWS", "values": values})

    def _values_append(self, title: str, values: list[list[Any]]) -> None:
        if values:
            self._request("POST", f"{SHEETS_API}/{self._spreadsheet_id()}/values/{title}!A1:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS", payload={"majorDimension": "ROWS", "values": values})

    def _replace_sheet(self, title: str, headers: list[str], rows: list[list[Any]]) -> None:
        # values.update does not clear trailing rows.  Clear first so deleted
        # chunks cannot survive in the managed current table.
        self._request("POST", f"{SHEETS_API}/{self._spreadsheet_id()}/values/{title}!A:ZZ:clear", payload={})
        self._values_update(f"{title}!A1", [headers, *rows])

    @staticmethod
    def _as_mapping(headers: list[str], row: list[str]) -> dict[str, str]:
        return {key: row[index] if index < len(row) else "" for index, key in enumerate(headers)}

    def _project_rows(self, title: str, headers: list[str], project_id: str) -> list[tuple[int, dict[str, str]]]:
        values = self._values_get(title)
        return [(number, self._as_mapping(headers, row)) for number, row in enumerate(values[1:], start=2) if row and row[0] == project_id]

    def project_initialized(self, project_id: str) -> bool:
        return any(row.get("key") == f"project:{project_id}:revision" for _, row in self._project_rows("Meta", META_HEADERS, f"project:{project_id}:revision"))

    def write_project_state(
        self, *, project_id: str, files: list[dict[str, Any]], changed_documents: dict[str, list[dict[str, Any]]], archived: list[dict[str, Any]], revision: str
    ) -> dict[str, int]:
        """Replace changed documents only; returns sheet rows for the local ID map."""
        self.ensure_schema()
        current = self._project_rows("Chunks_Current", CHUNK_HEADERS, project_id)
        changed_ids = set(changed_documents) | {str(row.get("document_id", "")) for row in archived}
        retained = [row for _, row in current if row["document_id"] not in changed_ids]
        appended: list[dict[str, Any]] = []
        for document_id, chunks in changed_documents.items():
            del document_id
            appended.extend(chunks)
        current_rows = [[row.get(header, "") for header in CHUNK_HEADERS] for row in [*retained, *appended]]
        # Chunks_Current is a managed table. Rewriting it gives deterministic row numbers for vector maps.
        all_other = [self._as_mapping(CHUNK_HEADERS, row) for row in self._values_get("Chunks_Current")[1:] if row and row[0] != project_id]
        self._replace_sheet("Chunks_Current", CHUNK_HEADERS, [[row.get(header, "") for header in CHUNK_HEADERS] for row in [*all_other, *retained, *appended]])
        other_files = [self._as_mapping(FILE_HEADERS, row) for row in self._values_get("Files")[1:] if row and row[0] != project_id]
        self._replace_sheet("Files", FILE_HEADERS, [[row.get(header, "") for header in FILE_HEADERS] for row in [*other_files, *files]])
        if archived:
            self._values_append("Chunks_History", [[row.get(header, "") for header in HISTORY_HEADERS] for row in archived])
        meta_rows = [row for row in self._values_get("Meta")[1:] if row and row[0] != f"project:{project_id}:revision"]
        self._replace_sheet("Meta", META_HEADERS, [*meta_rows, [f"project:{project_id}:revision", revision]])
        mapping = self._project_rows("Chunks_Current", CHUNK_HEADERS, project_id)
        row_map = {row["chunk_id"]: number for number, row in mapping}

        # Do not purge the local staging rows until the cloud write is visible
        # again with the expected IDs.  It makes an interrupted migration safe.
        expected_ids = [str(chunk["chunk_id"]) for chunks in changed_documents.values() for chunk in chunks]
        if expected_ids:
            verified: list[dict[str, Any]] = []
            for start in range(0, len(expected_ids), 100):
                verified.extend(self.fetch_chunks(project_id, expected_ids[start:start + 100], row_map))
            if {row["id"] for row in verified} != set(expected_ids):
                raise GoogleSheetsError("Google Sheets did not confirm the uploaded chunks")
        return row_map

    def fetch_chunks(self, project_id: str, chunk_ids: list[str], row_map: dict[str, int]) -> list[dict[str, Any]]:
        ranges = [f"Chunks_Current!A{row_map[chunk_id]}:R{row_map[chunk_id]}" for chunk_id in chunk_ids if chunk_id in row_map]
        if not ranges:
            return []
        query = "&".join(f"ranges={value}" for value in ranges)
        data = self._request("GET", f"{SHEETS_API}/{self._spreadsheet_id()}/values:batchGet?{query}")
        records: dict[str, dict[str, Any]] = {}
        for value_range in data.get("valueRanges", []):
            values = value_range.get("values", [])
            if values:
                row = self._as_mapping(CHUNK_HEADERS, [str(value) for value in values[0]])
                if row.get("project_id") == project_id:
                    records[row["chunk_id"]] = self._decode_chunk(row)
        return [records[chunk_id] for chunk_id in chunk_ids if chunk_id in records]

    def document_chunks(self, project_id: str, document_id: str) -> list[dict[str, Any]]:
        """Used only while synchronising a changed/deleted file, never by retrieval."""
        return [self._decode_chunk(row) for _, row in self._project_rows("Chunks_Current", CHUNK_HEADERS, project_id) if row.get("document_id") == document_id]

    def all_project_chunks(self, project_id: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
        rows = self._project_rows("Chunks_Current", CHUNK_HEADERS, project_id)
        return ([self._decode_chunk(row) for _, row in rows], {row["chunk_id"]: number for number, row in rows})

    @staticmethod
    def _decode_chunk(row: dict[str, str]) -> dict[str, Any]:
        def integer(value: str) -> int | None:
            try:
                return int(value) if value else None
            except ValueError:
                return None
        try:
            metadata = json.loads(row.get("metadata_json", "{}"))
        except json.JSONDecodeError:
            raise GoogleSheetsError("Google Sheets contains invalid chunk metadata")
        return {
            "id": row["chunk_id"], "document_id": row["document_id"], "relative_path": row["relative_path"],
            "ordinal": integer(row["ordinal"]) or 0, "text": row["text"], "metadata_json": json.dumps(metadata, ensure_ascii=False),
            "representation": row.get("representation", "classic"), "policy_fingerprint": row.get("policy_fingerprint", "legacy"),
            "source_sha256": row.get("source_sha256", ""), "indexed_at": row.get("indexed_at", ""),
            "page": integer(row["page"]), "heading": row["heading"] or None, "sheet": row["sheet"] or None,
            "cell_range": row["cell_range"] or None, "line_start": integer(row["line_start"]), "line_end": integer(row["line_end"]),
        }
