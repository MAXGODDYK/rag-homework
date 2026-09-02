from __future__ import annotations

"""Deterministic chunk representation policy for desktop RAG."""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ChunkingMode = Literal["classic", "developer", "mixed"]
CategoryMode = Literal["default", "classic", "developer", "mixed"]

CATEGORIES = ("code", "web_markup", "config_data", "documents", "tables", "notebooks", "plain_text")
CODE_EXTENSIONS = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".css", ".scss", ".vue", ".svelte", ".cs", ".java", ".kt", ".kts", ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".php", ".rb", ".swift", ".dart", ".lua", ".sql", ".ps1", ".sh", ".bash", ".zsh", ".proto", ".gradle", ".fs", ".fsx"}
WEB_EXTENSIONS = {".html", ".htm", ".xml"}
CONFIG_EXTENSIONS = {".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".odt", ".odp", ".epub"}
TABLE_EXTENSIONS = {".xlsx", ".ods", ".csv", ".tsv"}

# Query words only route a Mixed pair. They do not affect blocking, parsing or
# any other safety control. Code has a developer fallback by design.
DEVELOPER_QUERY = re.compile(
    r"\b(code|bug|error|exception|function|class|method|selector|css|html|tag|attribute|script|style|api|config|yaml|json|toml|sql|import|dependency|line|patch|fix|refactor|код|ошибк|функц|класс|тег|атрибут|стил|скрипт|конфиг|зависим|строк|исправ|помилк|функц|клас|тег|атрибут|рядк)\b",
    re.IGNORECASE,
)


def category_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in CODE_EXTENSIONS or name in {"dockerfile", "makefile"}:
        return "code"
    if suffix in WEB_EXTENSIONS:
        return "web_markup"
    if suffix in CONFIG_EXTENSIONS:
        return "config_data"
    if suffix == ".ipynb":
        return "notebooks"
    if suffix in DOCUMENT_EXTENSIONS:
        return "documents"
    if suffix in TABLE_EXTENSIONS:
        return "tables"
    return "plain_text"


@dataclass(frozen=True)
class ChunkingPolicy:
    global_mode: ChunkingMode = "classic"
    code: CategoryMode = "default"
    web_markup: CategoryMode = "default"
    config_data: CategoryMode = "default"
    documents: CategoryMode = "default"
    tables: CategoryMode = "default"
    notebooks: CategoryMode = "default"
    plain_text: CategoryMode = "default"

    def configured_mode(self, category: str) -> ChunkingMode:
        selected = getattr(self, category)
        if selected != "default":
            return selected
        # Source code must preserve its source form unless the user explicitly
        # overrides the category setting.
        return "developer" if category == "code" else self.global_mode

    def representations_for(self, path: Path) -> tuple[str, ...]:
        mode = self.configured_mode(category_for_path(path))
        return ("classic", "developer") if mode == "mixed" else (mode,)

    @property
    def fingerprint(self) -> str:
        payload = {"global_mode": self.global_mode, **{category: getattr(self, category) for category in CATEGORIES}}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]

    def representation_for_query(self, question: str, paths: list[str]) -> str:
        # A project containing only developer chunks must always retrieve them.
        if DEVELOPER_QUERY.search(question):
            return "developer"
        if paths and all(category_for_path(Path(path)) == "code" for path in paths):
            return "developer"
        return "classic"


def load_chunking_policy() -> ChunkingPolicy:
    def mode(name: str, default: str) -> str:
        value = os.getenv(name, default).strip().lower()
        return value if value in {"default", "classic", "developer", "mixed"} else default

    return ChunkingPolicy(
        global_mode=mode("JARVIS_CHUNKING_GLOBAL_MODE", "classic"),  # type: ignore[arg-type]
        **{category: mode(f"JARVIS_CHUNKING_{category.upper()}", "default") for category in CATEGORIES},  # type: ignore[arg-type]
    )
