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
    runtime = build_runtime()
    client = TestClient(create_app(runtime, "known-token"))
    headers = {"X-Jarvis-Token": "known-token"}
    created = client.post("/v1/sessions", headers=headers, json={"user_id": "desktop-owner", "title": "Keep this chat"})
    session_id = created.json()["id"]
    runtime.database.add_message(session_id, "user", "Preserved message")

    renamed = client.patch(f"/v1/sessions/{session_id}", headers=headers, json={"title": "  Renamed   chat  "})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed chat"
    assert client.patch(f"/v1/sessions/{session_id}", headers=headers, json={"title": "   "}).status_code == 422

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
    assert [row["content"] for row in client.get(f"/v1/sessions/{session_id}/messages", headers=headers).json()] == ["Preserved message"]


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


def test_same_project_name_is_allowed_for_different_folders(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("JARVIS_MIN_FREE_DISK_GB", "1")
    first_root = tmp_path / "a" / "project"
    second_root = tmp_path / "b" / "project"
    first_root.mkdir(parents=True)
    second_root.mkdir(parents=True)
    client = TestClient(create_app(build_runtime(), "known-token"))
    headers = {"X-Jarvis-Token": "known-token"}

    first = client.post("/v1/projects", headers=headers, json={"name": "project", "root_path": str(first_root)}).json()
    second = client.post("/v1/projects", headers=headers, json={"name": "project", "root_path": str(second_root)}).json()

    assert first["id"] != second["id"]
    assert len(client.get("/v1/projects", headers=headers).json()) == 2


def test_legacy_duplicate_projects_are_grouped_with_alias_ids(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("JARVIS_MIN_FREE_DISK_GB", "1")
    runtime = build_runtime()
    root = str((tmp_path / "legacy-project").resolve())
    first = runtime.database.create_project("desktop-owner", "Legacy", root)
    # Simulate records made by an old JARVIS version before path deduplication.
    runtime.database.execute(
        "INSERT INTO projects(id,user_id,name,root_path,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        ("project_legacy_alias", "desktop-owner", "Legacy", root, "2025-01-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00"),
    )
    runtime.database.create_session("desktop-owner", first["id"], "Primary chat")
    runtime.database.create_session("desktop-owner", "project_legacy_alias", "Alias chat")
    client = TestClient(create_app(runtime, "known-token"))
    headers = {"X-Jarvis-Token": "known-token"}

    projects = client.get("/v1/projects", headers=headers).json()
    sessions = client.get("/v1/sessions", headers=headers).json()

    assert len(projects) == 1
    assert set(projects[0]["alias_ids"]) == {first["id"], "project_legacy_alias"}
    assert {session["project_id"] for session in sessions} == set(projects[0]["alias_ids"])
