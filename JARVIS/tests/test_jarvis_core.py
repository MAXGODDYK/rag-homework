from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from jarvis.agent import AgentService
from jarvis.approvals import ApprovalManager, ApprovalError
from jarvis.config import JarvisConfig
from jarvis.database import Database
from jarvis.models import AgentMode, FileScope, LocalSettingsUpdate, RiskLevel, SessionPolicy
from jarvis.security import PathGuard, SecurityError, SessionPolicyStore
from jarvis.settings_store import update_local_settings
from jarvis.tool_runner import ToolRunner
from jarvis.tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec
from jarvis.tools.calculations import CalculatorInput, calculate
from jarvis.cli import parser


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
        google_access_token="",
        microsoft_client_id="",
        microsoft_tenant_id="common",
        microsoft_access_token="",
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


def test_sidecar_cli_accepts_desktop_parent_pid() -> None:
    args = parser().parse_args([
        "serve", "--parent-pid", "1234", "--config-root", "C:/config", "--state-root", "C:/state"
    ])
    assert args.parent_pid == 1234
    assert args.config_root == "C:/config" and args.state_root == "C:/state"


def test_local_settings_are_allowlisted_write_only_and_clearable(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    placeholder = "unit-test-placeholder"
    monkeypatch.delenv("FREEMODEL_API_KEY", raising=False)
    update_local_settings(
        config,
        LocalSettingsUpdate(freemodel_api_key=placeholder, freemodel_model="auto"),
    )
    body = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "FREEMODEL_API_KEY" in body and placeholder in body
    assert "freemodel_api_key" not in LocalSettingsUpdate().model_dump(exclude_none=True)

    update_local_settings(config, LocalSettingsUpdate(clear=["freemodel_api_key"]))
    assert "FREEMODEL_API_KEY" not in (tmp_path / ".env").read_text(encoding="utf-8")
    assert "FREEMODEL_API_KEY" not in __import__("os").environ


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


def test_math_prefilter_uses_calculator_before_final_answer(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    database = make_database(config)
    session = database.create_session("owner", None, "Math flow")
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="calculator",
            description="safe arithmetic",
            input_model=CalculatorInput,
            risk=RiskLevel.CALCULATE,
            handler=calculate,
        )
    )
    approvals = ApprovalManager(database)
    policies = SessionPolicyStore()
    provider = FakeProvider(
        [{"action": "final", "answer": "1017", "grounded": False}]
    )
    agent = AgentService(
        config=config,
        database=database,
        registry=registry,
        runner=ToolRunner(database, registry, approvals),
        approvals=approvals,
        retriever=EmptyRetriever(),
        policies=policies,
        providers={"local": provider},
    )

    answer = agent.answer(session["id"], "Calculate (125 * 8) + 17")
    assert answer.tool_run_ids
    run = database.query_one(
        "SELECT * FROM tool_runs WHERE id=?", (answer.tool_run_ids[0],)
    )
    assert run and run["tool_name"] == "calculator" and run["status"] == "completed"


def test_high_risk_requires_button_then_local_code_and_cannot_replay(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    database = make_database(config)
    session = database.create_session("owner", None, "High risk")
    manager = ApprovalManager(database)
    database.execute(
        "INSERT INTO tool_runs(id,session_id,tool_name,risk_level,status,input_json,created_at) VALUES(?,?,?,?,?,?,datetime('now'))",
        ("run", session["id"], "demo", "high_risk", "awaiting_approval", "{}"),
    )
    approval, code = manager.create(session["id"], "run", "Exact action", True)
    assert code and approval["status"] == "pending"
    with pytest.raises(ApprovalError):
        manager.confirm_code(approval["id"], code)
    assert manager.confirm_button(approval["id"])["status"] == "button_confirmed"
    with pytest.raises(ApprovalError):
        manager.confirm_code(approval["id"], "000000" if code != "000000" else "999999")
    assert manager.confirm_code(approval["id"], code)["status"] == "confirmed"
    manager.mark_executed(approval["id"])
    with pytest.raises(ApprovalError):
        manager.confirm_button(approval["id"])
