from __future__ import annotations

from pathlib import Path


DESKTOP_SOURCE = Path(__file__).resolve().parents[1] / "desktop" / "src"


def test_workspace_has_only_the_chat_column() -> None:
    app = (DESKTOP_SOURCE / "App.tsx").read_text(encoding="utf-8")
    main = (DESKTOP_SOURCE / "main.tsx").read_text(encoding="utf-8")

    assert 'className="project-panel"' not in app
    assert 'className="bottom-panel"' not in app
    assert "api.graph(" not in app
    assert "ReactFlow" not in app + main
    assert "monaco-editor" not in app + main


def test_chat_switch_discards_a_stale_history_response() -> None:
    app = (DESKTOP_SOURCE / "App.tsx").read_text(encoding="utf-8")

    assert "let cancelled = false;" in app
    assert "if (!cancelled) { setMessages(nextMessages); setLoadingMessages(false); }" in app
    assert "return () => { cancelled = true; };" in app
    assert "setMessages([]);" in app


def test_desktop_api_reconnects_after_backend_restart() -> None:
    api = (DESKTOP_SOURCE / "api.ts").read_text(encoding="utf-8")

    assert "for (let attempt = 0; attempt < 3; attempt += 1)" in api
    assert "attempt * 250" in api
    assert "this.info = undefined;" in api
    assert 'invoke<BackendInfo>("ensure_backend")' in api
    assert 'socket.addEventListener("close"' in api
