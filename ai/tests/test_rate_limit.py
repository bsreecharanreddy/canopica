"""Unit tests for the public demo's per-session daily rate limiter (Task 9
plan, Step 3) -- sits in front of the whole tiered `LlmClient` chain, so a
visitor over the limit gets a clean message, never a raw upstream 429.
"""

from __future__ import annotations

from typing import Any

from canopica_ai.common.rate_limit import RateLimitExceededError, SessionRateLimiter
from canopica_ai.config import Settings


def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {"public_demo_daily_request_limit_per_session": 3}
    defaults.update(overrides)
    return Settings(**defaults)


class TestWithinLimit:
    def test_a_first_request_is_allowed(self) -> None:
        limiter = SessionRateLimiter(_settings())

        limiter.check_and_increment("session-a")  # must not raise

    def test_requests_up_to_the_limit_are_all_allowed(self) -> None:
        limiter = SessionRateLimiter(_settings())

        limiter.check_and_increment("session-a")
        limiter.check_and_increment("session-a")
        limiter.check_and_increment("session-a")  # 3rd of a limit of 3

    def test_different_sessions_have_independent_limits(self) -> None:
        limiter = SessionRateLimiter(_settings())

        for _ in range(3):
            limiter.check_and_increment("session-a")
        limiter.check_and_increment("session-b")  # must not raise


class TestOverLimit:
    def test_the_request_beyond_the_limit_is_blocked(self) -> None:
        limiter = SessionRateLimiter(_settings())
        for _ in range(3):
            limiter.check_and_increment("session-a")

        try:
            limiter.check_and_increment("session-a")
        except RateLimitExceededError:
            pass
        else:
            raise AssertionError("expected RateLimitExceededError")

    def test_a_blocked_session_stays_blocked_on_further_attempts(self) -> None:
        limiter = SessionRateLimiter(_settings())
        for _ in range(3):
            limiter.check_and_increment("session-a")
        for _ in range(2):
            try:
                limiter.check_and_increment("session-a")
            except RateLimitExceededError:
                pass
            else:
                raise AssertionError("expected RateLimitExceededError")


class TestDailyReset:
    def test_a_new_day_resets_a_session_that_was_previously_over_limit(self) -> None:
        limiter = SessionRateLimiter(_settings())
        for _ in range(3):
            limiter.check_and_increment("session-a")

        # Simulate the day having rolled over -- directly, rather than
        # monkeypatching time, matching this repo's own
        # test_openrouter_tiered_client.py's month-rollover test, which
        # pre-seeds a stale month value rather than mocking the clock.
        _, count = limiter._counts["session-a"]
        assert count == 3
        limiter._counts["session-a"] = ("2000-01-01", count)

        limiter.check_and_increment("session-a")  # must not raise
