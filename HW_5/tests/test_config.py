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
    constants_path.write_text(
        'OPENAI_API_KEY = "local-key"\n'
        'FREEMODEL_API_KEY = "freemodel-local-key"\n'
        'LOCAL_ADAPTER_PATH = r"C:\\\\adapter"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FREEMODEL_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_ADAPTER_PATH", raising=False)
    monkeypatch.setattr(
        settings_module,
        "LOCAL_CONSTANTS_PATH",
        constants_path,
    )

    settings = load_settings()

    assert settings.openai_api_key == "local-key"
    assert settings.freemodel_api_key == "freemodel-local-key"
    assert settings.local_adapter_path == Path(r"C:\adapter")


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
    assert settings.local_model_name == "Qwen/Qwen3-4B-Instruct-2507"
    assert settings.telegram_network_timeout_seconds == 30.0
