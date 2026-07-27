from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str = ""


class BotRateLimiter:
    def __init__(
        self,
        state_path: Path,
        per_user_limit: int,
        window_seconds: int,
        openai_daily_limit: int,
    ) -> None:
        self.state_path = state_path
        self.per_user_limit = per_user_limit
        self.window_seconds = window_seconds
        self.openai_daily_limit = openai_daily_limit
        self._requests: dict[int, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _today(self) -> str:
        return date.today().isoformat()

    def _load_daily_state(self) -> dict[str, int | str]:
        if not self.state_path.exists():
            return {"date": self._today(), "openai_requests": 0}

        try:
            payload = json.loads(
                self.state_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return {"date": self._today(), "openai_requests": 0}

        if payload.get("date") != self._today():
            return {"date": self._today(), "openai_requests": 0}

        count = payload.get("openai_requests", 0)
        if not isinstance(count, int) or count < 0:
            count = 0
        return {"date": self._today(), "openai_requests": count}

    def _save_daily_state(self, state: dict[str, int | str]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.state_path)

    def check_and_record(
        self,
        user_id: int,
        provider_name: str,
        now_timestamp: float | None = None,
    ) -> RateLimitDecision:
        if now_timestamp is None:
            now_timestamp = datetime.now(
                timezone.utc
            ).timestamp()

        with self._lock:
            requests = self._requests[user_id]
            boundary = now_timestamp - self.window_seconds
            while requests and requests[0] <= boundary:
                requests.popleft()

            if len(requests) >= self.per_user_limit:
                return RateLimitDecision(
                    False,
                    (
                        f"Ліміт: {self.per_user_limit} запитів "
                        f"за {self.window_seconds // 60} хвилин."
                    ),
                )

            if provider_name == "openai":
                state = self._load_daily_state()
                current_count = int(state["openai_requests"])
                if current_count >= self.openai_daily_limit:
                    return RateLimitDecision(
                        False,
                        "Глобальний денний ліміт OpenAI вичерпано.",
                    )
                state["openai_requests"] = current_count + 1
                self._save_daily_state(state)

            requests.append(now_timestamp)
            return RateLimitDecision(True)

    def openai_daily_usage(self) -> tuple[int, int]:
        with self._lock:
            state = self._load_daily_state()
            return int(state["openai_requests"]), self.openai_daily_limit
