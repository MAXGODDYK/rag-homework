from __future__ import annotations

from pathlib import Path

from jarvis.config import JarvisConfig
from jarvis.database import Database


def make_config(tmp_path: Path) -> JarvisConfig:
    state = tmp_path / "state"
    return JarvisConfig(
        project_root=tmp_path,
        state_root=state,
        database_path=state / "jarvis.sqlite3",
        max_upload_bytes=100 * 1024 * 1024,
        max_extracted_bytes=500 * 1024 * 1024,
        max_archive_files=10_000,
        max_user_storage_bytes=1024**3,
        max_total_storage_bytes=5 * 1024**3,
        minimum_free_disk_bytes=1,
    )


def make_database(config: JarvisConfig) -> Database:
    database = Database(config.database_path)
    database.initialize()
    database.ensure_user("owner", "Owner")
    return database
