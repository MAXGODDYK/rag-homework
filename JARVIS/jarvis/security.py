from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from .config import JarvisConfig
from .models import AgentMode, FileScope, RiskLevel, SessionPolicy


SENSITIVE_PATH_PATTERN = re.compile(
    r"(?:^|[\\/])(?:\.env|\.ssh|\.aws|\.azure|credentials|secrets?|tokens?)(?:[\\/]|$)",
    re.IGNORECASE,
)


class SecurityError(RuntimeError):
    """Safe permission or path validation failure."""


class SessionPolicyStore:
    def __init__(self) -> None:
        self._policies: dict[str, SessionPolicy] = {}
        self._lock = RLock()

    def get(self, session_id: str) -> SessionPolicy:
        with self._lock:
            return self._policies.get(session_id, SessionPolicy()).model_copy(deep=True)

    def set(self, session_id: str, policy: SessionPolicy) -> SessionPolicy:
        with self._lock:
            self._policies[session_id] = policy.model_copy(deep=True)
            return policy.model_copy(deep=True)

    def reset(self, session_id: str) -> SessionPolicy:
        return self.set(session_id, SessionPolicy())


@dataclass(frozen=True)
class PathDecision:
    resolved_path: Path
    sensitive: bool
    requires_high_risk: bool


class PathGuard:
    def __init__(self, config: JarvisConfig) -> None:
        self.config = config

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_drive_root(path: Path) -> bool:
        return path.parent == path

    def validate(
        self,
        raw_path: str,
        scope: FileScope,
        workspace_root: Path | None,
        destructive: bool = False,
    ) -> PathDecision:
        if not raw_path.strip() or "$" in raw_path or "%" in raw_path:
            raise SecurityError("Path must be explicit and cannot contain unresolved variables")

        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            if workspace_root is None:
                raise SecurityError("Relative path requires an active workspace")
            candidate = workspace_root / candidate
        resolved = candidate.resolve(strict=False)

        if destructive and self._is_drive_root(resolved):
            raise SecurityError("Destructive operations against a drive root are never representable")

        allowed = False
        if scope == FileScope.COMPUTER:
            allowed = True
        elif scope == FileScope.WORKSPACE and workspace_root is not None:
            allowed = self._is_within(resolved, workspace_root.resolve())
        elif scope == FileScope.ROOTS:
            allowed = any(self._is_within(resolved, root) for root in self.config.allowed_roots)

        if not allowed:
            raise SecurityError(f"Path is outside the selected scope: {resolved}")

        sensitive = bool(SENSITIVE_PATH_PATTERN.search(str(resolved)))
        return PathDecision(
            resolved_path=resolved,
            sensitive=sensitive,
            requires_high_risk=sensitive or (destructive and scope == FileScope.COMPUTER),
        )


def requires_approval(mode: AgentMode, risk: RiskLevel) -> bool:
    if risk == RiskLevel.HIGH_RISK:
        return True
    if mode == AgentMode.SAFE:
        return risk in {
            RiskLevel.WRITE,
            RiskLevel.EXECUTE,
            RiskLevel.EXTERNAL_MUTATION,
        }
    return False


def generate_local_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_local_code(code: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), salt, 120_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_local_code(code: str, encoded: str) -> bool:
    try:
        salt_hex, expected_hex = encoded.split(":", 1)
        actual = hashlib.pbkdf2_hmac(
            "sha256", code.encode("utf-8"), bytes.fromhex(salt_hex), 120_000
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False
