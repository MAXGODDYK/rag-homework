from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from config.settings import PROJECT_ROOT, load_settings


def _local_constant(name: str, default: str = "") -> str:
    environment = os.getenv(name)
    if environment is not None:
        return environment.strip()

    constants_path = PROJECT_ROOT / "local_config" / "constants.py"
    if not constants_path.exists():
        return default

    namespace: dict[str, object] = {}
    exec(compile(constants_path.read_text(encoding="utf-8"), str(constants_path), "exec"), namespace)
    value = namespace.get(name, default)
    return str(value).strip()


def _integer(name: str, default: int) -> int:
    raw = _local_constant(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _ids(name: str) -> frozenset[int]:
    raw = _local_constant(name)
    if not raw:
        return frozenset()
    try:
        return frozenset(int(item.strip()) for item in raw.split(",") if item.strip())
    except ValueError as error:
        raise ValueError(f"{name} must contain comma-separated integers") from error


def _paths(name: str) -> tuple[Path, ...]:
    raw = _local_constant(name)
    if not raw:
        return ()
    return tuple(Path(item.strip()).expanduser().resolve() for item in raw.split(";") if item.strip())


@dataclass(frozen=True)
class JarvisConfig:
    project_root: Path
    state_root: Path
    database_path: Path
    authorized_telegram_user_ids: frozenset[int]
    admin_telegram_user_ids: frozenset[int]
    allowed_roots: tuple[Path, ...]
    max_upload_bytes: int
    max_extracted_bytes: int
    max_archive_files: int
    max_user_storage_bytes: int
    max_total_storage_bytes: int
    minimum_free_disk_bytes: int
    web_search_api_key: str
    google_client_id: str
    google_client_secret: str
    microsoft_client_id: str
    microsoft_tenant_id: str


def load_jarvis_config() -> JarvisConfig:
    # Load the legacy settings first so .env and local constants use one precedence model.
    load_settings()
    state_root = Path(
        _local_constant("JARVIS_STATE_ROOT", str(PROJECT_ROOT / "local_state"))
    ).expanduser().resolve()
    return JarvisConfig(
        project_root=PROJECT_ROOT.resolve(),
        state_root=state_root,
        database_path=state_root / "jarvis.sqlite3",
        authorized_telegram_user_ids=_ids("AUTHORIZED_TELEGRAM_USER_IDS"),
        admin_telegram_user_ids=_ids("ADMIN_TELEGRAM_USER_IDS"),
        allowed_roots=_paths("JARVIS_ALLOWED_ROOTS"),
        max_upload_bytes=_integer("JARVIS_MAX_UPLOAD_MB", 100) * 1024 * 1024,
        max_extracted_bytes=_integer("JARVIS_MAX_EXTRACTED_MB", 500) * 1024 * 1024,
        max_archive_files=_integer("JARVIS_MAX_ARCHIVE_FILES", 10000),
        max_user_storage_bytes=_integer("JARVIS_MAX_USER_STORAGE_MB", 1024) * 1024 * 1024,
        max_total_storage_bytes=_integer("JARVIS_MAX_TOTAL_STORAGE_MB", 5120) * 1024 * 1024,
        minimum_free_disk_bytes=_integer("JARVIS_MIN_FREE_DISK_GB", 20) * 1024 * 1024 * 1024,
        web_search_api_key=_local_constant("WEB_SEARCH_API_KEY"),
        google_client_id=_local_constant("GOOGLE_CLIENT_ID"),
        google_client_secret=_local_constant("GOOGLE_CLIENT_SECRET"),
        microsoft_client_id=_local_constant("MICROSOFT_CLIENT_ID"),
        microsoft_tenant_id=_local_constant("MICROSOFT_TENANT_ID", "common"),
    )
