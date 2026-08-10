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
        freemodel_daily_limit: int = 100,
    ) -> None:
        self.state_path = state_path
        self.per_user_limit = per_user_limit
        self.window_seconds = window_seconds
        self.openai_daily_limit = openai_daily_limit
        self.freemodel_daily_limit = freemodel_daily_limit
        self._requests: dict[int, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _today(self) -> str:
        return date.today().isoformat()

    def _load_daily_state(self) -> dict[str, int | str]:
        if not self.state_path.exists():
            return self._empty_daily_state()

        try:
            payload = json.loads(
                self.state_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return self._empty_daily_state()

        if payload.get("date") != self._today():
            return self._empty_daily_state()

        state = self._empty_daily_state()
        for field in ("openai_requests", "freemodel_requests"):
            count = payload.get(field, 0)
            if isinstance(count, int) and count >= 0:
                state[field] = count
        return state

    def _empty_daily_state(self) -> dict[str, int | str]:
        return {
            "date": self._today(),
            "openai_requests": 0,
            "freemodel_requests": 0,
        }

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

            daily_limits = {
                "openai": self.openai_daily_limit,
                "freemodel": self.freemodel_daily_limit,
            }
            if provider_name in daily_limits:
                state = self._load_daily_state()
                field = f"{provider_name}_requests"
                current_count = int(state[field])
                if current_count >= daily_limits[provider_name]:
                    return RateLimitDecision(
                        False,
                        "Глобальний денний ліміт "
                        f"{provider_name} вичерпано.",
                    )
                state[field] = current_count + 1
                self._save_daily_state(state)

            requests.append(now_timestamp)
            return RateLimitDecision(True)

    def openai_daily_usage(self) -> tuple[int, int]:
        return self.daily_usage("openai")

    def freemodel_daily_usage(self) -> tuple[int, int]:
        return self.daily_usage("freemodel")

    def daily_usage(self, provider_name: str) -> tuple[int, int]:
        limits = {
            "openai": self.openai_daily_limit,
            "freemodel": self.freemodel_daily_limit,
        }
        if provider_name not in limits:
            raise ValueError(f"Daily limit is not configured: {provider_name}")
        with self._lock:
            state = self._load_daily_state()
            return (
                int(state[f"{provider_name}_requests"]),
                limits[provider_name],
            )
