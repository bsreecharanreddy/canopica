"""Per-session daily rate limiter for the public demo's request path (Task
9 plan, Step 3) -- sits in front of the whole tiered `LlmClient` chain, so
a visitor over the limit gets a clean UX message from `public_demo/app.py`,
never a raw upstream 429 from OpenRouter.

In-memory, not persisted: unlike `llm_client.py`'s spend cap, this limit
exists for UX/anti-abuse, not cost control, so it doesn't need to survive
a restart -- a visitor mid-day after a redeploy simply gets a fresh count,
which is the safe direction to be wrong in.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from canopica_ai.config import Settings


class RateLimitExceededError(RuntimeError):
    """`session_id` has reached its daily request cap. `public_demo/app.py`
    renders this as a clean rate-limit message, never a raw upstream
    error."""


def _current_day_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


class SessionRateLimiter:
    """One process-wide limiter shared by every request `public_demo/
    app.py` handles. A `threading.Lock` guards the shared count dict --
    FastAPI runs sync request handlers in a thread pool, the same
    concurrency `llm_client.py`'s `_spend_lock` exists for."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[str, int]] = {}

    def check_and_increment(self, session_id: str) -> None:
        today = _current_day_key()
        with self._lock:
            day, count = self._counts.get(session_id, (today, 0))
            if day != today:
                count = 0
            if count >= self._settings.public_demo_daily_request_limit_per_session:
                raise RateLimitExceededError(
                    f"session {session_id!r} has reached its daily limit of "
                    f"{self._settings.public_demo_daily_request_limit_per_session} requests"
                )
            self._counts[session_id] = (today, count + 1)
