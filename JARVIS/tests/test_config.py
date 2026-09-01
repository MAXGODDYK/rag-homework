from __future__ import annotations

from pathlib import Path

import config.settings as settings_module
from config.settings import load_settings


def test_environment_has_priority(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("FREEMODEL_API_KEY", "freemodel-environment-key")
    monkeypatch.setenv("FREEMODEL_MODEL", "auto-test")

    settings = load_settings()

    assert settings.openai_api_key == "environment-key"
    assert settings.openai_model == "test-model"
    assert settings.freemodel_api_key == "freemodel-environment-key"
    assert settings.freemodel_model == "auto-test"


def test_local_constants_are_used_when_environment_is_absent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    constants_path = tmp_path / "constants.py"
    freemodel_key_name = "FREEMODEL_API_KEY"
    constants_path.write_text(
        'OPENAI_API_KEY = "local-key"\n'
        f'{freemodel_key_name} = "freemodel-local-key"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FREEMODEL_API_KEY", raising=False)
    monkeypatch.setattr(
        settings_module,
        "LOCAL_CONSTANTS_PATH",
        constants_path,
    )

    settings = load_settings()

    assert settings.openai_api_key == "local-key"
    assert settings.freemodel_api_key == "freemodel-local-key"


def test_public_defaults_are_used_without_private_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr(
        settings_module,
        "LOCAL_CONSTANTS_PATH",
        tmp_path / "missing.py",
    )

    settings = load_settings()

    assert settings.openai_model == "gpt-4.1-mini"
    assert settings.freemodel_base_url == "https://api.freemodel.dev/v1"
    assert settings.freemodel_model == "auto"
    assert settings.embedding_model_name == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert settings.reranker_model_name == "BAAI/bge-reranker-v2-m3"
