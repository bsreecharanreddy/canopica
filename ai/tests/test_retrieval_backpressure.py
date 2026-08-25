"""OpenSearch's ml-commons circuit breaker is *backpressure*, not a
failure -- these prove `hybrid_search` treats it that way.

Unlike test_retrieval.py (which is `e2e` and needs the real stack), these
drive a fake client, because the condition under test is one this project
cannot summon on demand against a live cluster: it depends on where the
JVM happens to be in its GC cycle at the instant a query lands.

Confirmed live, CI run 32810042677's `ai-eval` job. The eval ran 11
minutes of real retrieval and then died on a `hybrid_search` with
`TransportError(429, 'circuit_breaking_exception', 'Memory Circuit
Breaker is open, please check your resources!')`. The diagnostics ported
into that job in the previous commit are what finally made it
attributable, and they rule out every standing theory:

  * every OpenSearch *core* breaker reported `tripped: 0` (request,
    fielddata, in_flight_requests, parent) -- so this is ml-commons' own
    breaker, not one of OpenSearch's;
  * of ml-commons' three, the message names this one: the disk breaker
    says "Disk Circuit Breaker", the host-RAM one says "Native Memory
    Circuit Breaker". Plain "Memory Circuit Breaker" is the JVM-heap
    breaker, `plugins.ml_commons.jvm_heap_memory_threshold`, which
    search_pipeline.py already raised 85 -> 92;
  * and it is transient, not a live-set problem: the JVM logged a GC
    3 seconds after the failure ("spent [391ms] collecting in the last
    [1.5s]") and the heap read **18%** one second after that.

So the heap sawtoothed past 92%, ml-commons sampled `heapUsedPercent` at
the peak, and a ~400ms collection then reclaimed nearly all of it. The
garbage was never pressure. Raising the threshold again would only move
the dice -- the sawtooth's peak approaches 100% by construction, and 85
-> 92 had already failed to fix exactly this. A 429 is by definition a
"retry shortly" signal, and one GC is all "shortly" needs to mean.
"""

from __future__ import annotations

import time
from typing import Any, cast

import pytest
from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError, TransportError

from canopica_ai.config import Settings
from canopica_ai.policy_intelligence import retrieval
from canopica_ai.policy_intelligence.retrieval import hybrid_search

_BREAKER_ERROR = TransportError(
    429,
    "circuit_breaking_exception",
    "Memory Circuit Breaker is open, please check your resources!",
)

_ONE_HIT = {
    "hits": {
        "hits": [
            {
                "_id": "273.9(a)-0",
                "_score": 1.0,
                "_source": {
                    "cfr_section": "273.9(a)",
                    "heading": "Income eligibility standards",
                    "text": "Households shall meet the gross income test.",
                },
            }
        ]
    }
}


class _FakeClient:
    """Raises `error` for the first `failures` calls, then returns a hit."""

    def __init__(self, failures: int, error: Exception = _BREAKER_ERROR) -> None:
        self._failures = failures
        self._error = error
        self.calls = 0

    def search(self, **_: Any) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self._failures:
            raise self._error
        return _ONE_HIT

    def as_client(self) -> OpenSearch:
        """`hybrid_search` only ever calls `.search()` on what it is given,
        so a stub with that one method is a faithful stand-in. The cast is
        the narrowest way to say that under `mypy --strict` without
        loosening the production signature to `Any` for the tests' sake."""
        return cast(OpenSearch, self)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither of this module's two real network dependencies is the thing
    under test. Ollama is stubbed out so no embedding call is made, and
    tracing is disabled for the reason `Settings.otel_enabled` documents --
    with no Jaeger listening, every span close would block on a retrying
    exporter, which is the bug the previous commit fixed."""
    monkeypatch.setenv("CANOPICA_OTEL_ENABLED", "false")
    monkeypatch.setattr(retrieval, "embed_text", lambda text, settings: [0.1] * 8)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


def test_a_tripped_breaker_is_retried_rather_than_failing_the_caller() -> None:
    """The whole point: one GC-peak sample must not fail an 11-minute eval
    run, or a CI-blocking gate flakes on the JVM's collection timing."""
    client = _FakeClient(failures=1)

    results = hybrid_search("gross income test", settings=Settings(), client=client.as_client())

    assert client.calls == 2
    assert [r.cfr_section for r in results] == ["273.9(a)"]


def test_a_breaker_that_never_clears_still_raises() -> None:
    """Retry is not suppression. A cluster genuinely out of heap must
    still fail the gate rather than spin forever -- the CI signal this
    project relies on is only worth having if it can still go red."""
    client = _FakeClient(failures=99)

    with pytest.raises(TransportError) as excinfo:
        hybrid_search("gross income test", settings=Settings(), client=client.as_client())

    assert excinfo.value.status_code == 429
    assert client.calls == retrieval._MAX_SEARCH_ATTEMPTS


def test_a_non_backpressure_error_is_not_retried() -> None:
    """A missing index is a real bug, not congestion. Retrying it would
    hide the cause behind several seconds of pointless backoff and report
    it as the wrong kind of problem."""
    client = _FakeClient(failures=99, error=NotFoundError(404, "index_not_found_exception", "x"))

    with pytest.raises(NotFoundError):
        hybrid_search("gross income test", settings=Settings(), client=client.as_client())

    assert client.calls == 1
