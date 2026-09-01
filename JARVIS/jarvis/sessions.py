from __future__ import annotations

from threading import RLock

from .models import SessionPolicy


class SessionPolicyStore:
    """Volatile desktop-RAG settings for each open conversation."""

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
