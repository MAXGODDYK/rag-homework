from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from .approvals import ApprovalManager
from .database import Database
from .models import ApprovalStatus, RiskLevel, new_id, utc_now
from .security import requires_approval
from .tools.base import ToolContext, ToolExecutionError, ToolRegistry, ToolResult


SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|token|password|secret|authorization|cookie)", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


@dataclass(frozen=True)
class ToolRunOutcome:
    tool_run_id: str
    status: str
    risk: RiskLevel
    result: ToolResult | None = None
    approval: dict[str, Any] | None = None
    local_code: str | None = None


class ToolRunner:
    def __init__(
        self,
        database: Database,
        registry: ToolRegistry,
        approvals: ApprovalManager,
    ) -> None:
        self.database = database
        self.registry = registry
        self.approvals = approvals

    def propose(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolRunOutcome:
        spec = self.registry.get(tool_name)
        available, reason = spec.availability()
        if not available:
            raise ToolExecutionError(f"{tool_name} is unavailable: {reason}")
        validated = spec.validate(arguments)
        if context.policy.scope.value not in spec.scopes:
            raise ToolExecutionError(
                f"{tool_name} is not allowed in scope {context.policy.scope.value}"
            )
        risk = spec.effective_risk(validated, context)
        tool_run_id = new_id("toolrun")
        now = utc_now().isoformat()
        safe_input = redact(validated.model_dump(mode="json"))
        self.database.execute(
            """
            INSERT INTO tool_runs(
                id, session_id, tool_name, risk_level, status, input_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_run_id,
                context.session_id,
                tool_name,
                risk.value,
                "proposed",
                json.dumps(safe_input, ensure_ascii=False),
                now,
            ),
        )
        # Keep validated arguments only in process memory for immediate execution. For
        # approval flows the original request is reconstructed from caller-owned state.
        if requires_approval(context.policy.mode, risk):
            approval, local_code = self.approvals.create(
                context.session_id,
                tool_run_id,
                spec.preview(validated, context),
                high_risk=risk == RiskLevel.HIGH_RISK,
            )
            self.database.execute(
                "UPDATE tool_runs SET status=? WHERE id=?",
                ("awaiting_approval", tool_run_id),
            )
            return ToolRunOutcome(
                tool_run_id=tool_run_id,
                status="awaiting_approval",
                risk=risk,
                approval=approval,
                local_code=local_code,
            )
        return self._execute(tool_run_id, spec, validated, context, risk)

    def execute_confirmed(
        self,
        approval_id: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolRunOutcome:
        approval = self.approvals.get(approval_id)
        if approval["session_id"] != context.session_id:
            raise ToolExecutionError("Approval belongs to another session")
        if approval["status"] != ApprovalStatus.CONFIRMED.value:
            raise ToolExecutionError("Approval is not confirmed")
        run = self.database.query_one("SELECT * FROM tool_runs WHERE id=?", (approval["tool_run_id"],))
        if run is None:
            raise ToolExecutionError("Approved tool run does not exist")
        spec = self.registry.get(run["tool_name"])
        validated = spec.validate(arguments)
        risk = spec.effective_risk(validated, context)
        if risk.value != run["risk_level"]:
            raise ToolExecutionError("Tool risk changed after approval")
        outcome = self._execute(run["id"], spec, validated, context, risk)
        self.approvals.mark_executed(approval_id)
        return outcome

    def _execute(
        self,
        tool_run_id: str,
        spec,
        validated: BaseModel,
        context: ToolContext,
        risk: RiskLevel,
    ) -> ToolRunOutcome:
        self.database.execute(
            "UPDATE tool_runs SET status=? WHERE id=?",
            ("running", tool_run_id),
        )
        try:
            result = spec.handler(validated, context)
        except ToolExecutionError:
            self.database.execute(
                "UPDATE tool_runs SET status=?, error_type=?, finished_at=? WHERE id=?",
                ("failed", "ToolExecutionError", utc_now().isoformat(), tool_run_id),
            )
            raise
        except Exception as error:
            self.database.execute(
                "UPDATE tool_runs SET status=?, error_type=?, finished_at=? WHERE id=?",
                ("failed", type(error).__name__, utc_now().isoformat(), tool_run_id),
            )
            raise ToolExecutionError(f"{spec.name} failed safely") from error
        self.database.execute(
            "UPDATE tool_runs SET status=?, output_json=?, finished_at=? WHERE id=?",
            (
                "completed",
                json.dumps(redact(result.model_dump(mode="json")), ensure_ascii=False),
                utc_now().isoformat(),
                tool_run_id,
            ),
        )
        return ToolRunOutcome(
            tool_run_id=tool_run_id,
            status="completed",
            risk=risk,
            result=result,
        )
