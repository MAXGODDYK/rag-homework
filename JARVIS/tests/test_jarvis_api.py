from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from jarvis.api import create_app
from jarvis.runtime import build_runtime


def test_local_api_requires_ipc_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("JARVIS_MIN_FREE_DISK_GB", "1")
    runtime = build_runtime()
    client = TestClient(create_app(runtime, "known-token"))

    assert client.get("/v1/health").status_code == 401
    response = client.get("/v1/health", headers={"X-Jarvis-Token": "known-token"})
    assert response.status_code == 200
    assert response.json()["mode"] == "desktop-rag-only"


def test_sessions_store_only_rag_provider_and_corpus_policy(monkeypatch, tmp_path: Path) -> None:
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
        "provider_profile": "local",
        "source_selector": "auto",
    }
    changed = client.post(
        f"/v1/sessions/{session_id}/policy",
        headers=headers,
        json={"provider_profile": "extractive", "source_selector": "notes.md"},
    )
    assert changed.status_code == 200
    assert changed.json() == {"provider_profile": "extractive", "source_selector": "notes.md"}


def test_desktop_api_does_not_expose_tool_or_approval_routes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("JARVIS_MIN_FREE_DISK_GB", "1")
    client = TestClient(create_app(build_runtime(), "known-token"))
    headers = {"X-Jarvis-Token": "known-token"}

    assert client.get("/v1/tools", headers=headers).status_code == 404
    assert client.post("/v1/approvals/demo/cancel", headers=headers).status_code == 404
