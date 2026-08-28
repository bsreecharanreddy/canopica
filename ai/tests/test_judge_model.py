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
from pydantic import BaseModel

from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.eval import judge_model
from canopica_ai.policy_intelligence.eval.judge_model import OpenRouterJudgeModel

_SETTINGS = Settings(openrouter_api_key="test-key")


def _response(url: str, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("POST", url))


def _status_response(
    url: str, status_code: int, payload: dict[str, Any] | None = None
) -> httpx.Response:
    """A genuine non-2xx HTTP status, distinct from `_response`'s 200-with-
    `error`-body shape -- OpenRouter uses both across its own stack (an
    upstream provider error comes back wrapped in a 200; a request its own
    edge rejects outright comes back as a real status code), and this
    project has now seen both live.

    `payload` carries OpenRouter's own explanation of the status, which is
    the only place the *reason* for a 404 is ever stated -- the status line
    itself is identical whether the model does not exist or no provider
    endpoint happens to be free at that instant."""
    request = httpx.Request("POST", url)
    if payload is None:
        return httpx.Response(status_code, request=request)
    return httpx.Response(status_code, json=payload, request=request)


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


class TestATransportLevelFailureIsRetried:
    """A fourth, structurally different failure shape from the three
    above: `httpx.post()` itself raising, never returning a `response` at
    all. Every branch above this point in `generate()` only ever runs
    once a response exists, so a connection dropped mid-request skipped
    `_RETRYABLE_ERROR_CODES` entirely.

    Found live (2026-08-27) during local verification of the eval-gate
    baseline fix: all 12 questions had already answered and 8 had already
    judged cleanly, then `httpx.RemoteProtocolError: peer closed
    connection without sending complete message body (incomplete chunked
    read)` crashed the run outright on the next judge call."""

    def test_a_transport_error_is_retried_and_a_later_success_is_returned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise httpx.RemoteProtocolError("peer closed connection without complete body")
            return _response(url, {"choices": [{"message": {"content": "grounded verdict"}}]})

        monkeypatch.setattr(httpx, "post", fake_post)

        result = OpenRouterJudgeModel(_SETTINGS).generate("grade this")

        assert result == "grounded verdict"
        assert calls == 3

    def test_a_persistent_transport_error_exhausts_retries_and_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ConnectTimeout("connection timed out")

        monkeypatch.setattr(httpx, "post", fake_post)

        with pytest.raises(RuntimeError, match="connection timed out"):
            OpenRouterJudgeModel(_SETTINGS).generate("grade this")

        assert calls == judge_model._MAX_ATTEMPTS


class TestRealHttpStatusErrorsAreRetriedToo:
    """A real, live gap found 2026-08-25: OpenRouter doesn't always wrap a
    provider error in a 200 response -- a request its own edge rejects can
    come back as a genuine non-2xx status (a live CI run hit a real 404).
    `TestTransientUpstreamOverloadIsRetried` above only ever fakes the
    200-with-error-body shape, so it could not have caught this."""

    def test_a_real_502_status_is_retried_and_a_later_success_is_returned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return _status_response(url, 502)
            return _response(url, {"choices": [{"message": {"content": "grounded verdict"}}]})

        monkeypatch.setattr(httpx, "post", fake_post)

        result = OpenRouterJudgeModel(_SETTINGS).generate("grade this")

        assert result == "grounded verdict"
        assert calls == 3

class TestAFourOhFourIsTransientForAFreeModel:
    """**This reverses a decision made earlier the same day** (2026-08-25),
    and the reversal is the point, so it is worth stating why rather than
    quietly flipping a constant.

    That earlier round found OpenRouter's non-2xx shape for the first time
    and, reasonably, treated 404 as "the model does not exist" -- the
    textbook reading, and non-retryable. Then the identical 404 discarded a
    second CI run (`32811993194`) after **24m39s** of completed work: all
    eight questions had finished retrieval and generation, and the failure
    landed on `contextual_recall`, i.e. after judge calls had already been
    succeeding against that very model in that very run.

    Three live probes settle what the status line alone cannot: the pinned
    model is present in OpenRouter's public model list; a plain chat call
    to it returns 200; and a call carrying the exact `json_schema`
    structured-output shape DeepEval sends also returns 200. A model that
    does not exist cannot do any of those. What is left is OpenRouter's
    documented behaviour for a `:free` variant -- no provider endpoint free
    at that instant, surfaced as a 404 -- which is transient by definition.

    The payoff is sharply asymmetric, which is what makes retrying the
    right default rather than merely permissible: a genuinely missing model
    now fails on the first call within seconds *and says so*, because the
    error carries OpenRouter's own explanation (below); a transient one
    otherwise throws away a 25-minute run and a full set of judge calls.
    """

    def test_a_404_is_retried_and_a_later_success_is_returned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 2:
                return _status_response(
                    url, 404, {"error": {"message": "No endpoints found", "code": 404}}
                )
            return _response(url, {"choices": [{"message": {"content": "grounded verdict"}}]})

        monkeypatch.setattr(httpx, "post", fake_post)

        result = OpenRouterJudgeModel(_SETTINGS).generate("grade this")

        assert result == "grounded verdict"
        assert calls == 2

    def test_a_persistent_404_still_raises_and_carries_openrouters_reason(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Retrying must not cost the diagnosis. The old message was just
        the status line and reason phrase, which is why the CI failure that
        prompted this could not be attributed from the log at all -- the
        body is the only place OpenRouter distinguishes "no endpoints
        available right now" from "no such model"."""

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            return _status_response(
                url, 404, {"error": {"message": "No endpoints found", "code": 404}}
            )

        monkeypatch.setattr(httpx, "post", fake_post)

        with pytest.raises(RuntimeError, match="No endpoints found"):
            OpenRouterJudgeModel(_SETTINGS).generate("grade this")

    def test_a_client_configuration_error_is_still_not_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The guard the reversed test above was really protecting: a
        deterministic client-side error must still fail on the first
        attempt. A bad API key will never succeed on attempt four, and
        burning three backoffs before saying so helps nobody."""
        calls = 0

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            return _status_response(url, 401, {"error": {"message": "No auth credentials"}})

        monkeypatch.setattr(httpx, "post", fake_post)

        with pytest.raises(RuntimeError, match="401"):
            OpenRouterJudgeModel(_SETTINGS).generate("grade this")

        assert calls == 1


class TestAResponseThatIsNotLoadableJsonIsRetried:
    """The third shape of "the upstream provider returned garbage", after
    the 200-with-`error`-body and the real non-2xx above, and the one that
    looks least like a failure: HTTP 200, no `error` key, a `content`
    string present -- just not JSON, despite `response_format:
    json_schema` with `strict: true` having been sent.

    Found live in run `32935635062`: all eight questions answered, then one
    `contextual_precision` judge call came back this way and DeepEval's
    `trimAndLoadJson` raised `ValueError: Evaluation LLM outputted an
    invalid JSON`, discarding ~19 minutes of finished work over one bad
    response out of roughly a dozen.
    """

    class _Verdict(BaseModel):
        verdict: str

    @staticmethod
    def _scripted(responses: list[dict[str, Any]]) -> tuple[Any, list[int]]:
        calls = [0]

        def fake_post(
            url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float
        ) -> httpx.Response:
            payload = responses[calls[0]]
            calls[0] += 1
            return _response(url, payload)

        return fake_post, calls

    def test_prose_instead_of_json_is_retried_and_a_later_success_is_returned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prose = {"choices": [{"message": {"content": "Sure! Here is my assessment: it is good."}}]}
        valid = {"choices": [{"message": {"content": '{"verdict": "yes"}'}}]}
        fake_post, calls = self._scripted([prose, valid])
        monkeypatch.setattr(httpx, "post", fake_post)

        result = OpenRouterJudgeModel(_SETTINGS).generate("grade this", schema=self._Verdict)

        assert result == '{"verdict": "yes"}'
        assert calls[0] == 2

    def test_truncated_json_is_retried_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A cut-off response has a `{` but no closing brace -- the shape a
        # provider produces when it hits its own output limit mid-object.
        truncated = {"choices": [{"message": {"content": '{"verdict": "ye'}}]}
        valid = {"choices": [{"message": {"content": '{"verdict": "yes"}'}}]}
        fake_post, calls = self._scripted([truncated, valid])
        monkeypatch.setattr(httpx, "post", fake_post)

        result = OpenRouterJudgeModel(_SETTINGS).generate("grade this", schema=self._Verdict)

        assert result == '{"verdict": "yes"}'
        assert calls[0] == 2

    def test_a_fenced_json_block_is_accepted_not_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # DeepEval's own `trimAndLoadJson` takes first-`{` to last-`}`, so a
        # markdown-fenced object loads fine there. Rejecting it here would
        # be stricter than the consumer and would retry working responses.
        fenced = '```json\n{"verdict": "yes"}\n```'
        fake_post, calls = self._scripted([{"choices": [{"message": {"content": fenced}}]}])
        monkeypatch.setattr(httpx, "post", fake_post)

        result = OpenRouterJudgeModel(_SETTINGS).generate("grade this", schema=self._Verdict)

        assert result == fenced
        assert calls[0] == 1

    def test_a_schemaless_call_accepts_a_plain_string_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # DeepEval also makes plain, unstructured calls through this same
        # adapter. Those have no JSON expectation at all, so the check must
        # not fire and turn a perfectly good answer into three retries.
        fake_post, calls = self._scripted([{"choices": [{"message": {"content": "just prose"}}]}])
        monkeypatch.setattr(httpx, "post", fake_post)

        result = OpenRouterJudgeModel(_SETTINGS).generate("grade this")

        assert result == "just prose"
        assert calls[0] == 1

    def test_persistent_garbage_raises_carrying_the_offending_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prose = {"choices": [{"message": {"content": "I cannot comply with that."}}]}
        fake_post, calls = self._scripted([prose] * judge_model._MAX_ATTEMPTS)
        monkeypatch.setattr(httpx, "post", fake_post)

        # The body verbatim, not just "invalid JSON" -- whether the provider
        # returned a refusal, prose, or truncation is the entire diagnosis.
        with pytest.raises(RuntimeError, match="I cannot comply with that"):
            OpenRouterJudgeModel(_SETTINGS).generate("grade this", schema=self._Verdict)

        assert calls[0] == judge_model._MAX_ATTEMPTS
