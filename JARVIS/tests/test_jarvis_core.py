from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from jarvis.agent import AgentService
from jarvis.approvals import ApprovalManager, ApprovalError
from jarvis.config import JarvisConfig
from jarvis.database import Database
from jarvis.models import AgentMode, FileScope, RiskLevel, SessionPolicy
from jarvis.security import PathGuard, SecurityError, SessionPolicyStore
from jarvis.tool_runner import ToolRunner
from jarvis.tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec


def make_config(tmp_path: Path) -> JarvisConfig:
    state = tmp_path / "state"
    return JarvisConfig(
        project_root=tmp_path,
        state_root=state,
        database_path=state / "jarvis.sqlite3",
        authorized_telegram_user_ids=frozenset(),
        admin_telegram_user_ids=frozenset(),
        allowed_roots=(tmp_path,),
        max_upload_bytes=100 * 1024 * 1024,
        max_extracted_bytes=500 * 1024 * 1024,
        max_archive_files=10_000,
        max_user_storage_bytes=1024**3,
        max_total_storage_bytes=5 * 1024**3,
        minimum_free_disk_bytes=1,
        web_search_api_key="",
        google_client_id="",
        google_client_secret="",
        microsoft_client_id="",
        microsoft_tenant_id="common",
    )


def make_database(config: JarvisConfig) -> Database:
    database = Database(config.database_path)
    database.initialize()
    database.ensure_user("owner", "Owner")
    return database


def test_session_policy_is_memory_only_and_resets() -> None:
    store = SessionPolicyStore()
    changed = SessionPolicy(mode=AgentMode.AUTONOMOUS, scope=FileScope.COMPUTER)
    store.set("session", changed)
    assert store.get("session") == changed
    assert store.reset("session") == SessionPolicy()


def test_path_guard_enforces_scope_and_sensitive_paths(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    guard = PathGuard(config)

    decision = guard.validate("notes.txt", FileScope.WORKSPACE, workspace)
    assert decision.resolved_path == workspace / "notes.txt"
    assert decision.sensitive is False

    (workspace / ".env").write_text("SECRET=x", encoding="utf-8")
    assert guard.validate(".env", FileScope.WORKSPACE, workspace).requires_high_risk
    with pytest.raises(SecurityError):
        guard.validate(str(tmp_path / "outside.txt"), FileScope.WORKSPACE, workspace)


class WriteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


def write_handler(value: WriteInput, _context: ToolContext) -> ToolResult:
    return ToolResult(content=value.value, data={"value": value.value})


class FakeProvider:
    name = "local"

    def __init__(self, responses: list[dict]) -> None:
        self.responses = iter(responses)

    def availability(self) -> tuple[bool, str]:
        return True, "fake"

    def generate(self, _prompt: str) -> str:
        return json.dumps(next(self.responses))


class EmptyRetriever:
    def search(self, *args, **kwargs):
        return []


def test_safe_approval_executes_then_resumes_agent(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    database = make_database(config)
    session = database.create_session("owner", None, "Approval flow")
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="write_demo",
            description="test write",
            input_model=WriteInput,
            risk=RiskLevel.WRITE,
            handler=write_handler,
        )
    )
    approvals = ApprovalManager(database)
    runner = ToolRunner(database, registry, approvals)
    policies = SessionPolicyStore()
    provider = FakeProvider(
        [
            {"action": "tool", "tool_name": "write_demo", "arguments": {"value": "done"}},
            {"action": "final", "answer": "Completed", "grounded": False},
        ]
    )
    agent = AgentService(
        config=config,
        database=database,
        registry=registry,
        runner=runner,
        approvals=approvals,
        retriever=EmptyRetriever(),
        policies=policies,
        providers={"local": provider},
    )

    pending = agent.answer(session["id"], "Please perform the write")
    assert pending.pending_approval_id
    approvals.confirm_button(pending.pending_approval_id)
    outcome, answer = agent.execute_confirmed(pending.pending_approval_id)
    assert outcome.result and outcome.result.data == {"value": "done"}
    assert answer.answer.endswith("Completed")
    assert approvals.get(pending.pending_approval_id)["status"] == "executed"
    with pytest.raises(ApprovalError):
        approvals.confirm_button(pending.pending_approval_id)

