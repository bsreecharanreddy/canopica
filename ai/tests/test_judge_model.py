"""Unit tests for the OpenRouter eval-judge adapter's retry behavior.

No real network: `httpx.post` is swapped for a scripted stub, matching
`test_llm_client.py`'s own capture-not-mock approach. Motivated by a real,
live failure (2026-08-24): a clean 8-question eval run got through every
question's retrieval and generation, then died on `OpenRouter judge call
failed: {'message': 'Upstream error from Nvidia: Service temporarily
overloaded', 'code': 502}` -- a transient free-tier upstream issue with
nothing wrong in this project's own request. A CI-blocking gate has no
business flaking on that when a short retry would very plausibly have
succeeded.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.eval import judge_model
from canopica_ai.policy_intelligence.eval.judge_model import OpenRouterJudgeModel

_SETTINGS = Settings(openrouter_api_key="test-key")


def _response(url: str, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("POST", url))


@pytest.fixture(autouse=True)
def _no_real_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    # These tests assert retry *behavior*, not real wall-clock backoff --
    # sleeping for real would make a unit test pay the exact per-call cost
    # this fix exists to absorb only once, for real, in production. Set by
    # dotted path, not attribute access, since judge_model doesn't
    # explicitly re-export the stdlib `time` module it imports.
    monkeypatch.setattr(
        "canopica_ai.policy_intelligence.eval.judge_model.time.sleep", lambda seconds: None
    )


class TestTransientUpstreamOverloadIsRetried:
    def test_a_502_is_retried_and_a_later_success_is_returned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        overloaded = {
            "error": {
                "message": "Upstream error from Nvidia: Service temporarily overloaded",
                "code": 502,
            }
        }
        responses: list[dict[str, Any]] = [
            overloaded,
            overloaded,
            {"choices": [{"message": {"content": "grounded verdict"}}]},
        ]
        calls = 0

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            nonlocal calls
            payload = responses[calls]
            calls += 1
            return _response(url, payload)

        monkeypatch.setattr(httpx, "post", fake_post)

        result = OpenRouterJudgeModel(_SETTINGS).generate("grade this")

        assert result == "grounded verdict"
        assert calls == 3

    def test_retries_are_exhausted_and_the_error_is_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            return _response(url, {"error": {"message": "still overloaded", "code": 502}})

        monkeypatch.setattr(httpx, "post", fake_post)

        with pytest.raises(RuntimeError, match="still overloaded"):
            OpenRouterJudgeModel(_SETTINGS).generate("grade this")

        assert calls == judge_model._MAX_ATTEMPTS

    def test_a_non_retryable_error_is_raised_on_the_first_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            return _response(url, {"error": {"message": "bad request", "code": 400}})

        monkeypatch.setattr(httpx, "post", fake_post)

        with pytest.raises(RuntimeError, match="bad request"):
            OpenRouterJudgeModel(_SETTINGS).generate("grade this")

        assert calls == 1
