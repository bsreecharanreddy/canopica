"""Unit tests for the public demo's tiered `LlmClient` (Task 9 plan, Step 1).

No real network: `httpx.post` is swapped for a scripted stub, matching
`test_llm_client.py`/`test_judge_model.py`'s own capture-not-mock approach.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from canopica_ai.common import llm_client
from canopica_ai.common.llm_client import (
    InferenceUnavailableError,
    OpenRouterNotConfiguredError,
    OpenRouterTieredClient,
)
from canopica_ai.config import Settings

_FREE_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
_PAID_MODEL = "deepseek/deepseek-chat"


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "openrouter_api_key": "test-key",
        "openrouter_public_demo_free_model": _FREE_MODEL,
        "openrouter_public_demo_paid_model": _PAID_MODEL,
        "openrouter_public_demo_paid_input_price_per_mtok_usd": 1.0,
        "openrouter_public_demo_paid_output_price_per_mtok_usd": 2.0,
        "openrouter_public_demo_monthly_cap_usd": 5.0,
        "openrouter_public_demo_spend_file": tmp_path / "spend.json",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _ok(
    url: str, content: str, *, prompt_tokens: int = 100, completion_tokens: int = 50
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        },
        request=httpx.Request("POST", url),
    )


def _rate_limited(url: str) -> httpx.Response:
    return httpx.Response(
        429,
        json={"error": {"message": "rate-limited upstream", "code": 429}},
        request=httpx.Request("POST", url),
    )


def _upstream_error(url: str, status_code: int, *, wrapped: bool = False) -> httpx.Response:
    """A non-2xx upstream failure -- `wrapped=True` matches the 200-status,
    error-in-body shape OpenRouter also uses (the same two-shapes pattern
    `judge_model.py`'s own retry logic already handles), `wrapped=False`
    matches a genuine non-2xx HTTP status."""
    message = {"message": "Upstream error", "code": status_code}
    if wrapped:
        return httpx.Response(200, json={"error": message}, request=httpx.Request("POST", url))
    return httpx.Response(status_code, json={"error": message}, request=httpx.Request("POST", url))


class TestFreeTierSuccess:
    def test_a_clean_free_tier_response_is_returned_with_no_paid_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        models_called: list[str] = []

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            models_called.append(json["model"])
            return _ok(url, "a grounded free-tier answer")

        monkeypatch.setattr(httpx, "post", fake_post)

        response = OpenRouterTieredClient(_settings(tmp_path)).generate(
            "what is the gross income test?"
        )

        assert response.text == "a grounded free-tier answer"
        assert models_called == [_FREE_MODEL]

    def test_no_spend_is_recorded_on_a_free_tier_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings(tmp_path)
        monkeypatch.setattr(httpx, "post", lambda url, **_: _ok(url, "answer"))

        OpenRouterTieredClient(settings).generate("a question")

        assert not settings.openrouter_public_demo_spend_file.exists()


class TestFallbackOnRateLimit:
    def test_a_free_tier_rate_limit_falls_back_to_the_paid_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        models_called: list[str] = []

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            models_called.append(json["model"])
            if json["model"] == _FREE_MODEL:
                return _rate_limited(url)
            return _ok(url, "a grounded paid-tier answer")

        monkeypatch.setattr(httpx, "post", fake_post)

        response = OpenRouterTieredClient(_settings(tmp_path)).generate("a question")

        assert response.text == "a grounded paid-tier answer"
        assert models_called == [_FREE_MODEL, _PAID_MODEL]

    def test_the_paid_fallback_records_computed_spend(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings(tmp_path)

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            if json["model"] == _FREE_MODEL:
                return _rate_limited(url)
            # 100 prompt tokens @ $1/MTok + 50 completion tokens @ $2/MTok
            # = $0.0001 + $0.0001 = $0.0002
            return _ok(url, "answer", prompt_tokens=100, completion_tokens=50)

        monkeypatch.setattr(httpx, "post", fake_post)

        OpenRouterTieredClient(settings).generate("a question")

        recorded = json.loads(settings.openrouter_public_demo_spend_file.read_text())
        assert recorded["spent_usd"] == pytest.approx(0.0002)

    def test_spend_accumulates_across_calls_in_the_same_month(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings(tmp_path)

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            if json["model"] == _FREE_MODEL:
                return _rate_limited(url)
            return _ok(url, "answer", prompt_tokens=100, completion_tokens=50)

        monkeypatch.setattr(httpx, "post", fake_post)
        client = OpenRouterTieredClient(settings)

        client.generate("first question")
        client.generate("second question")

        recorded = json.loads(settings.openrouter_public_demo_spend_file.read_text())
        assert recorded["spent_usd"] == pytest.approx(0.0004)


class TestFallbackOnUpstreamOutage:
    """Found live (2026-08-26), not assumed: a real request against the
    public demo hit `nvidia/nemotron-3-ultra-550b-a55b:free` returning a
    genuine 502 ("Service temporarily overloaded"), which raised a raw
    `RuntimeError` instead of falling back -- `generate()` only caught
    `_RateLimitedError`, so any non-429 upstream failure skipped the paid
    tier entirely. Design doc §2.10's own "Tiered circuit breaker" is
    explicit that the fallback exists for both "once both are exhausted
    or on an upstream outage" -- a 502 is exactly that outage case, not
    only a 429. Fixed by widening what counts as retryable to match
    `judge_model.py`'s own already-established `_RETRYABLE_ERROR_CODES`
    for the identical OpenRouter error shape.
    """

    def test_a_free_tier_502_falls_back_to_the_paid_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        models_called: list[str] = []

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            models_called.append(json["model"])
            if json["model"] == _FREE_MODEL:
                return _upstream_error(url, 502)
            return _ok(url, "a grounded paid-tier answer")

        monkeypatch.setattr(httpx, "post", fake_post)

        response = OpenRouterTieredClient(_settings(tmp_path)).generate("a question")

        assert response.text == "a grounded paid-tier answer"
        assert models_called == [_FREE_MODEL, _PAID_MODEL]

    def test_a_free_tier_200_wrapped_502_falls_back_to_the_paid_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            if json["model"] == _FREE_MODEL:
                return _upstream_error(url, 502, wrapped=True)
            return _ok(url, "a grounded paid-tier answer")

        monkeypatch.setattr(httpx, "post", fake_post)

        response = OpenRouterTieredClient(_settings(tmp_path)).generate("a question")

        assert response.text == "a grounded paid-tier answer"

    def test_a_non_retryable_error_does_not_fall_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 400 is this project's own request, not an upstream outage --
        the paid tier would fail identically, so this should surface
        immediately rather than waste a paid-tier call."""
        models_called: list[str] = []

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            models_called.append(json["model"])
            return _upstream_error(url, 400)

        monkeypatch.setattr(httpx, "post", fake_post)

        with pytest.raises(httpx.HTTPStatusError, match="400"):
            OpenRouterTieredClient(_settings(tmp_path)).generate("a question")

        assert models_called == [_FREE_MODEL]


class TestMonthlyCap:
    def test_once_spend_meets_the_cap_the_paid_model_is_never_called(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings(tmp_path, openrouter_public_demo_monthly_cap_usd=1.0)
        settings.openrouter_public_demo_spend_file.write_text(
            json.dumps({"month": _current_month(), "spent_usd": 1.0})
        )
        models_called: list[str] = []

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            models_called.append(json["model"])
            return _rate_limited(url)

        monkeypatch.setattr(httpx, "post", fake_post)

        with pytest.raises(InferenceUnavailableError):
            OpenRouterTieredClient(settings).generate("a question")

        assert models_called == [_FREE_MODEL]

    def test_a_new_month_resets_the_counter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings(tmp_path, openrouter_public_demo_monthly_cap_usd=1.0)
        settings.openrouter_public_demo_spend_file.write_text(
            json.dumps({"month": "2000-01", "spent_usd": 1.0})
        )

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            if json["model"] == _FREE_MODEL:
                return _rate_limited(url)
            return _ok(url, "answer")

        monkeypatch.setattr(httpx, "post", fake_post)

        response = OpenRouterTieredClient(settings).generate("a question")

        assert response.text == "answer"


class TestBothTiersUnavailable:
    def test_a_rate_limited_paid_tier_raises_a_typed_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(httpx, "post", lambda url, **_: _rate_limited(url))

        with pytest.raises(InferenceUnavailableError):
            OpenRouterTieredClient(_settings(tmp_path)).generate("a question")


class TestConcurrentPaidTierAccounting:
    def test_concurrent_spend_updates_are_not_lost(self, tmp_path: Path) -> None:
        """A background security review of f42b46c (this client's initial
        commit) flagged `_add_spend`'s read-modify-write as a lost-update
        race, and the cap check ahead of it as a fail-open gap for the
        same underlying reason: nothing serialized two concurrent paid-tier
        calls, so both could read the same starting spend and each
        overwrite the other's update instead of adding to it. Confirmed
        live before the fix: a `threading.Barrier`-forced collision between
        `_add_spend` calls with no lock reliably left only $0.01 recorded
        for 5 concurrent $0.01 additions, not $0.05.

        `_spend_lock` fixes this by making the whole section a mutual-
        exclusion critical section, exactly as `generate()` uses it -- so
        with the lock held, the five threads below are serialized by
        construction and this assertion holds regardless of scheduling,
        not as a timing gamble the way the pre-fix reproduction was.
        """
        path = tmp_path / "spend.json"
        thread_count = 5

        def add_spend_as_generate_does() -> None:
            with llm_client._spend_lock(path):
                llm_client._add_spend(path, 0.01)

        threads = [threading.Thread(target=add_spend_as_generate_does) for _ in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert llm_client._read_spend(path) == pytest.approx(0.01 * thread_count)


class TestConfiguration:
    def test_missing_api_key_raises_at_construction(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path, openrouter_api_key=None)

        with pytest.raises(OpenRouterNotConfiguredError):
            OpenRouterTieredClient(settings)


def _current_month() -> str:
    return datetime.now(UTC).strftime("%Y-%m")
