from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from jarvis.api import create_app
from jarvis.config import JarvisConfig
from jarvis.runtime import build_runtime


def test_local_api_requires_ipc_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("JARVIS_MIN_FREE_DISK_GB", "1")
    runtime = build_runtime()
    client = TestClient(create_app(runtime, "known-token"))

    assert client.get("/v1/health").status_code == 401
    response = client.get("/v1/health", headers={"X-Jarvis-Token": "known-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_sessions_start_with_safe_workspace_policy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("JARVIS_MIN_FREE_DISK_GB", "1")
    runtime = build_runtime()
    client = TestClient(create_app(runtime, "known-token"))
    headers = {"X-Jarvis-Token": "known-token"}

    response = client.post(
        "/v1/sessions",
        headers=headers,
        json={"user_id": "desktop-owner", "title": "New"},
    )
    assert response.status_code == 200
    session_id = response.json()["id"]
    assert runtime.policies.get(session_id).model_dump(mode="json") == {
        "mode": "safe",
        "scope": "workspace",
        "provider_profile": "auto",
        "source_selector": "auto",
    }
