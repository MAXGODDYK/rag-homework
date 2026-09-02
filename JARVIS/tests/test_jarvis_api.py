from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from jarvis.api import create_app
from jarvis.models import Event
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


def test_chat_event_has_a_complete_runtime_schema() -> None:
    """A chat request must be able to publish its first lifecycle event."""
    event = Event(type="chat.started", session_id="session_demo")

    assert event.payload == {}


def test_project_sync_events_have_a_complete_runtime_schema() -> None:
    assert Event(type="project.syncing", session_id="session_demo").type == "project.syncing"
    assert Event(type="project.synced", payload={"updated": 1}).payload["updated"] == 1


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


def test_archived_conversation_is_hidden_until_restored(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("JARVIS_MIN_FREE_DISK_GB", "1")
    client = TestClient(create_app(build_runtime(), "known-token"))
    headers = {"X-Jarvis-Token": "known-token"}
    created = client.post("/v1/sessions", headers=headers, json={"user_id": "desktop-owner", "title": "Keep this chat"})
    session_id = created.json()["id"]

    archived = client.post(f"/v1/sessions/{session_id}/archive", headers=headers)

    assert archived.status_code == 200
    assert archived.json()["archived_at"]
    assert client.get("/v1/sessions", headers=headers).json() == []
    assert [row["id"] for row in client.get("/v1/sessions?archived=true", headers=headers).json()] == [session_id]
    assert client.post(f"/v1/messages?session_id={session_id}", headers=headers, json={"content": "still there?"}).status_code == 409

    restored = client.post(f"/v1/sessions/{session_id}/restore", headers=headers)

    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert [row["id"] for row in client.get("/v1/sessions", headers=headers).json()] == [session_id]


def test_duplicate_project_root_returns_the_existing_project(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("JARVIS_MIN_FREE_DISK_GB", "1")
    root = tmp_path / "same-project"
    root.mkdir()
    client = TestClient(create_app(build_runtime(), "known-token"))
    headers = {"X-Jarvis-Token": "known-token"}

    first = client.post("/v1/projects", headers=headers, json={"name": "Same project", "root_path": str(root)})
    duplicate = client.post("/v1/projects", headers=headers, json={"name": "Another label", "root_path": str(root / ".." / root.name)})

    assert first.status_code == duplicate.status_code == 200
    assert first.json()["id"] == duplicate.json()["id"]
    assert duplicate.json()["created"] is False
    assert len(client.get("/v1/projects", headers=headers).json()) == 1
