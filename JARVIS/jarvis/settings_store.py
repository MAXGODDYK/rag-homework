from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values

from config.settings import load_settings

from .config import JarvisConfig
from .models import LocalSettingsUpdate
from .rag_service import DesktopRagService


FIELD_TO_ENV = {
    "freemodel_api_key": "FREEMODEL_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "freemodel_model": "FREEMODEL_MODEL",
}


def _availability(rag: DesktopRagService) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for name in ("freemodel", "openai"):
        provider = rag.providers.get(name)
        if provider is None:
            result[name] = {"available": False, "reason": "not registered"}
            continue
        available, reason = provider.availability()
        result[name] = {"available": available, "reason": reason}
    return result


def public_settings_status(config: JarvisConfig, rag: DesktopRagService) -> dict[str, object]:
    settings = load_settings()
    return {
        "providers": _availability(rag),
        "configured": {
            "freemodel_api_key": bool(settings.freemodel_api_key),
            "openai_api_key": bool(settings.openai_api_key),
        },
        "models": {
            "freemodel": settings.freemodel_model,
            "openai": settings.openai_model,
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
