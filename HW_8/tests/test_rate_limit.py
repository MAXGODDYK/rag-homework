from __future__ import annotations

from scripts.telegram_bot.rate_limit import BotRateLimiter


def test_per_user_window_limit(tmp_path) -> None:
    limiter = BotRateLimiter(
        state_path=tmp_path / "usage.json",
        per_user_limit=2,
        window_seconds=10,
        openai_daily_limit=100,
    )

    assert limiter.check_and_record(1, "local", 1.0).allowed
    assert limiter.check_and_record(1, "local", 2.0).allowed
    assert not limiter.check_and_record(1, "local", 3.0).allowed
    assert limiter.check_and_record(1, "local", 12.0).allowed


def test_openai_daily_limit_is_persistent(tmp_path) -> None:
    state_path = tmp_path / "usage.json"
    first = BotRateLimiter(
        state_path=state_path,
        per_user_limit=10,
        window_seconds=600,
        openai_daily_limit=2,
    )

    assert first.check_and_record(1, "openai", 1.0).allowed
    assert first.check_and_record(2, "openai", 2.0).allowed

    second = BotRateLimiter(
        state_path=state_path,
        per_user_limit=10,
        window_seconds=600,
        openai_daily_limit=2,
    )
    assert not second.check_and_record(3, "openai", 3.0).allowed


def test_freemodel_daily_limit_is_independent_and_persistent(
    tmp_path,
) -> None:
    state_path = tmp_path / "usage.json"
    first = BotRateLimiter(
        state_path=state_path,
        per_user_limit=10,
        window_seconds=600,
        openai_daily_limit=3,
        freemodel_daily_limit=1,
    )

    assert first.check_and_record(1, "freemodel", 1.0).allowed
    assert first.check_and_record(2, "openai", 2.0).allowed

    second = BotRateLimiter(
        state_path=state_path,
        per_user_limit=10,
        window_seconds=600,
        openai_daily_limit=3,
        freemodel_daily_limit=1,
    )
    assert not second.check_and_record(3, "freemodel", 3.0).allowed
    assert second.freemodel_daily_usage() == (1, 1)
    assert second.openai_daily_usage() == (1, 3)
