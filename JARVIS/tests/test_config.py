from __future__ import annotations

from pathlib import Path

import config.settings as settings_module
from config.settings import load_settings


def test_environment_has_priority(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11500")
    monkeypatch.setenv("OLLAMA_MODEL", "environment-model")

    settings = load_settings()

    assert settings.ollama_base_url == "http://127.0.0.1:11500"
    assert settings.ollama_model == "environment-model"


def test_local_constants_are_used_when_environment_is_absent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    constants_path = tmp_path / "constants.py"
    constants_path.write_text(
        'OLLAMA_BASE_URL = "http://127.0.0.1:11500"\n'
        'OLLAMA_MODEL = "local-model"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.setattr(
        settings_module,
        "LOCAL_CONSTANTS_PATH",
        constants_path,
    )

    settings = load_settings()

    assert settings.ollama_base_url == "http://127.0.0.1:11500"
    assert settings.ollama_model == "local-model"


def test_public_defaults_are_used_without_private_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.setattr(
        settings_module,
        "LOCAL_CONSTANTS_PATH",
        tmp_path / "missing.py",
    )

    settings = load_settings()

    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_model == "qwen3:14b"
    assert settings.embedding_model_name == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert settings.reranker_model_name == "BAAI/bge-reranker-v2-m3"
