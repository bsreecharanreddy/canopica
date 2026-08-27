"""Hybrid (BM25 + k-NN) retrieval over the CFR corpus, fused by RRF and
reranked by a cross-encoder -- the sole read path every later Policy
Intelligence feature (Task 2's Q&A service, Task 7's eval harness) calls.
Neither talks to OpenSearch directly; this module is the only one that does.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from opensearchpy import OpenSearch
from opensearchpy.exceptions import TransportError
from opentelemetry.trace import Span
from pydantic import BaseModel

from canopica_ai.common.observability import traced_retrieval_call
from canopica_ai.config import Settings

# ml-commons rejects a search with HTTP 429 when its own memory circuit
# breaker is open. That is backpressure, not a failure: measured on this
# stack (CI run 32810042677), the JVM heap sawtoothed past the 92%
# threshold search_pipeline.py sets, ml-commons sampled `heapUsedPercent`
# at that peak, and a 391ms collection then dropped the heap to 18% --
# the garbage was never pressure. Retrying after one GC is the whole fix;
# raising the threshold again only moves the dice, since the sawtooth's
# peak approaches 100% by construction and 85 -> 92 had already failed at
# exactly this. See test_retrieval_backpressure.py for the full evidence.
#
# Deliberately keyed on the 429 *status*, not on the message: OpenSearch
# returns 429 for `circuit_breaking_exception` and for
# `es_rejected_execution_exception` (a full thread pool), which are the
# same "try again shortly" signal and want the same handling. Matching on
# the human-readable string instead would be brittle for no benefit.
_RETRYABLE_SEARCH_STATUS = 429
# 4 attempts / 2s-4s-6s (12s total backoff) held until `_CI_GATE_QUESTIONS`
# grew 8 -> 12 (2026-08-26): CI run 33037187113 exhausted all 4 attempts
# for real, heap still at 94% against the 92% threshold on the last one --
# 12s wasn't always enough headroom for GC to catch up under the heavier
# per-run reranker/hybrid-search load. Widened alongside the docker-compose
# heap bump (2g -> 3g) rather than instead of it: this buys the *retry*
# more time to wait out a slow collection, the heap bump buys more room
# before the threshold trips at all -- the same "handle the signal,
# don't just raise the limit" reasoning from the comment above applied to
# both knobs. Doubled attempts and raised the constant a further 50%
# rather than picking new numbers from scratch, so the ceiling (3+6+9+12+15
# = 45s) stays proportional to the ~400ms-3s collections actually observed
# and trivial against an eval run measured in minutes.
_MAX_SEARCH_ATTEMPTS = 6
_RETRY_BACKOFF_SECONDS = 3.0


class RetrievedChunk(BaseModel):
    cfr_section: str
    heading: str
    text: str
    chunk_id: str
    score: float


def embed_text(text: str, settings: Settings) -> list[float]:
    """Embeds one string via Ollama -- the same call used at indexing time
    (index.py) and at query time (hybrid_search below), so a query's
    embedding always comes from the same model/config that embedded the
    corpus it's compared against."""
    response = httpx.post(
        f"{settings.ollama_base_url}/api/embeddings",
        json={"model": settings.ollama_embedding_model, "prompt": text},
        timeout=60.0,
    )
    response.raise_for_status()
    embedding: list[float] = response.json()["embedding"]
    return embedding


def _client(settings: Settings) -> OpenSearch:
    return OpenSearch(hosts=[settings.opensearch_url])


def _search_with_backpressure_retry(
    client: OpenSearch,
    body: dict[str, Any],
    settings: Settings,
    span: Span,
) -> dict[str, Any]:
    """Issues the search, retrying only while ml-commons reports
    backpressure (see `_RETRYABLE_SEARCH_STATUS` above).

    Any other transport error propagates on the first attempt: a missing
    index or a malformed query is a real bug, and burning three backoffs
    before surfacing it would both slow the report down and dress a
    deterministic failure up as congestion.

    The retry count lands on the *existing* retrieval span rather than in
    a log line, so a run that succeeded only after backing off is still
    visibly distinguishable from one that never contended -- the same
    reason Task 8 instrumented this path at all.
    """
    for attempt in range(_MAX_SEARCH_ATTEMPTS):
        try:
            response: dict[str, Any] = client.search(
                index=settings.cfr_corpus_index,
                body=body,
                params={"search_pipeline": settings.cfr_search_pipeline},
            )
        except TransportError as error:
            is_last_attempt = attempt == _MAX_SEARCH_ATTEMPTS - 1
            if error.status_code != _RETRYABLE_SEARCH_STATUS or is_last_attempt:
                span.set_attribute("canopica.retrieval.backpressure_retries", attempt)
                raise
            time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue
        span.set_attribute("canopica.retrieval.backpressure_retries", attempt)
        return response
    raise AssertionError("unreachable: the loop above either returns or raises")


def hybrid_search(
    query: str,
    top_k: int = 5,
    *,
    settings: Settings | None = None,
    client: OpenSearch | None = None,
) -> list[RetrievedChunk]:
    """Issues one hybrid query (BM25 sub-query + k-NN sub-query over the
    query's own embedding) through the RRF-fusion + cross-encoder-rerank
    search pipeline (search_pipeline.py), returning the top-k reranked
    chunks."""
    settings = settings or Settings()
    client = client or _client(settings)

    # The span covers the query embedding *and* the search, because that
    # pair is what one retrieval costs. `embed_text` itself is left
    # uninstrumented on purpose: index.py calls it once per chunk in a
    # loop, and this project's exporter is a SimpleSpanProcessor (see
    # observability.py) which exports synchronously -- a span per chunk
    # would turn a corpus rebuild into thousands of blocking HTTP calls
    # to Jaeger for telemetry nobody reads.
    with traced_retrieval_call(index=settings.cfr_corpus_index, top_k=top_k) as span:
        query_vector = embed_text(query, settings)
        span.set_attribute("gen_ai.request.model", settings.ollama_embedding_model)

        body = {
            "size": top_k,
            "query": {
                "hybrid": {
                    "queries": [
                        {"match": {"text": {"query": query}}},
                        {"knn": {"embedding": {"vector": query_vector, "k": top_k * 4}}},
                    ]
                }
            },
            "ext": {"rerank": {"query_context": {"query_text": query}}},
        }

        response = _search_with_backpressure_retry(client, body, settings, span)

        chunks = [
            RetrievedChunk(
                cfr_section=hit["_source"]["cfr_section"],
                heading=hit["_source"]["heading"],
                text=hit["_source"]["text"],
                chunk_id=hit["_id"],
                score=hit["_score"],
            )
            for hit in response["hits"]["hits"]
        ]
        span.set_attribute("canopica.retrieval.chunk_count", len(chunks))
        return chunks
