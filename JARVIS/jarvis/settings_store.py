from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values

from config.settings import load_settings

from .agent import AgentService
from .config import JarvisConfig
from .models import LocalSettingsUpdate


FIELD_TO_ENV = {
    "freemodel_api_key": "FREEMODEL_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "hf_token": "HF_TOKEN",
    "web_search_api_key": "WEB_SEARCH_API_KEY",
    "google_access_token": "GOOGLE_ACCESS_TOKEN",
    "microsoft_access_token": "MICROSOFT_ACCESS_TOKEN",
    "local_adapter_path": "LOCAL_ADAPTER_PATH",
    "freemodel_model": "FREEMODEL_MODEL",
}


def _availability(agent: AgentService) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for name in ("freemodel", "openai", "local", "local-agent"):
        provider = agent.providers.get(name)
        if provider is None:
            result[name] = {"available": False, "reason": "not registered"}
            continue
        available, reason = provider.availability()
        result[name] = {"available": available, "reason": reason}
    return result


def public_settings_status(config: JarvisConfig, agent: AgentService) -> dict[str, object]:
    settings = load_settings()
    return {
        "providers": _availability(agent),
        "configured": {
            "freemodel_api_key": bool(settings.freemodel_api_key),
            "openai_api_key": bool(settings.openai_api_key),
            "telegram_bot_token": bool(settings.telegram_bot_token),
            "hf_token": bool(settings.hf_token),
            "web_search_api_key": bool(config.web_search_api_key),
            "google_access_token": bool(config.google_access_token),
            "microsoft_access_token": bool(config.microsoft_access_token),
            "local_adapter_path": bool(settings.local_adapter_path),
        },
        "models": {
            "freemodel": settings.freemodel_model,
            "openai": settings.openai_model,
            "local": settings.local_model_name,
        },
        "storage": str(config.project_root / ".env"),
    }


def update_local_settings(config: JarvisConfig, payload: LocalSettingsUpdate) -> Path:
    """Persist only allowlisted values; secret values are never returned by the API."""
    path = config.project_root / ".env"
    path.parent.mkdir(parents=True, exist_ok=True)
    current = {
        key: value
        for key, value in dotenv_values(path).items()
        if value is not None
    } if path.exists() else {}

    updates = payload.model_dump(exclude={"clear"}, exclude_none=True)
    for field, value in updates.items():
        clean = value.strip()
        if not clean:
            continue
        environment_name = FIELD_TO_ENV[field]
        current[environment_name] = clean
        # Make the new provider immediately available in the current backend process.
        os.environ[environment_name] = clean

    for field in payload.clear:
        environment_name = FIELD_TO_ENV[field]
        current.pop(environment_name, None)
        os.environ.pop(environment_name, None)

    temporary = path.with_suffix(".env.tmp")
    body = "\n".join(
        f"{key}={json.dumps(value, ensure_ascii=False)}"
        for key, value in sorted(current.items())
    )
    temporary.write_text(body + ("\n" if body else ""), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)
    return path
