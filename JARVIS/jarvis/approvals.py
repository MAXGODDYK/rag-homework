from __future__ import annotations

from datetime import timedelta

from .database import Database
from .models import ApprovalStatus, new_id, utc_now
from .security import generate_local_code, hash_local_code, verify_local_code


class ApprovalError(RuntimeError):
    """Safe approval state failure."""


class ApprovalManager:
    def __init__(self, database: Database, ttl_seconds: int = 300) -> None:
        self.database = database
        self.ttl_seconds = ttl_seconds

    def create(
        self,
        session_id: str,
        tool_run_id: str,
        preview: str,
        high_risk: bool,
    ) -> tuple[dict, str | None]:
        approval_id = new_id("approval")
        created_at = utc_now()
        expires_at = created_at + timedelta(seconds=self.ttl_seconds)
        code = generate_local_code() if high_risk else None
        code_hash = hash_local_code(code) if code else None
        self.database.execute(
            """
            INSERT INTO approvals(
                id, session_id, tool_run_id, status, high_risk, preview,
                code_hash, expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                session_id,
                tool_run_id,
                ApprovalStatus.PENDING.value,
                int(high_risk),
                preview,
                code_hash,
                expires_at.isoformat(),
                created_at.isoformat(),
            ),
        )
        return self.get(approval_id), code

    def get(self, approval_id: str) -> dict:
        approval = self.database.query_one("SELECT * FROM approvals WHERE id=?", (approval_id,))
        if approval is None:
            raise ApprovalError("Approval not found")
        return approval

    def _pending(self, approval_id: str) -> dict:
        approval = self.get(approval_id)
        if approval["status"] not in {
            ApprovalStatus.PENDING.value,
            ApprovalStatus.BUTTON_CONFIRMED.value,
        }:
            raise ApprovalError(f"Approval is already {approval['status']}")
        if utc_now().isoformat() > approval["expires_at"]:
            self.database.execute(
                "UPDATE approvals SET status=? WHERE id=?",
                (ApprovalStatus.EXPIRED.value, approval_id),
            )
            raise ApprovalError("Approval expired")
        return approval

    def confirm_button(self, approval_id: str) -> dict:
        approval = self._pending(approval_id)
        if approval["high_risk"]:
            self.database.execute(
                "UPDATE approvals SET status=? WHERE id=?",
                (ApprovalStatus.BUTTON_CONFIRMED.value, approval_id),
            )
            return self.get(approval_id)
        self.database.execute(
            "UPDATE approvals SET status=?, confirmed_at=? WHERE id=?",
            (ApprovalStatus.CONFIRMED.value, utc_now().isoformat(), approval_id),
        )
        return self.get(approval_id)

    def confirm_code(self, approval_id: str, code: str) -> dict:
        approval = self._pending(approval_id)
        if not approval["high_risk"]:
            raise ApprovalError("Local code is not required for this approval")
        if approval["status"] != ApprovalStatus.BUTTON_CONFIRMED.value:
            raise ApprovalError("Confirm the visible action before entering the local code")
        if not approval["code_hash"] or not verify_local_code(code, approval["code_hash"]):
            raise ApprovalError("Invalid local approval code")
        self.database.execute(
            "UPDATE approvals SET status=?, confirmed_at=? WHERE id=?",
            (ApprovalStatus.CONFIRMED.value, utc_now().isoformat(), approval_id),
        )
        return self.get(approval_id)

    def cancel(self, approval_id: str) -> dict:
        self._pending(approval_id)
        self.database.execute(
            "UPDATE approvals SET status=? WHERE id=?",
            (ApprovalStatus.CANCELLED.value, approval_id),
        )
        return self.get(approval_id)

    def mark_executed(self, approval_id: str) -> None:
        approval = self.get(approval_id)
        if approval["status"] != ApprovalStatus.CONFIRMED.value:
            raise ApprovalError("Approval is not confirmed")
        self.database.execute(
            "UPDATE approvals SET status=? WHERE id=?",
            (ApprovalStatus.EXECUTED.value, approval_id),
        )
