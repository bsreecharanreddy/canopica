"""Hybrid (BM25 + k-NN) retrieval over the SOP corpus, fused by RRF and
reranked by a cross-encoder -- the sole read path `service.py` calls.
Structurally identical to `policy_intelligence.retrieval.hybrid_search`
(same query shape, same backpressure-retry discipline against ml-commons'
circuit breaker -- see that module's own extensive comment for the real,
live-measured reasoning behind it), but a separate function against a
separate index (`settings.sop_corpus_index`) rather than a parameterized
version of the original: `RetrievedChunk`'s own field names (`cfr_section`,
a citation-shaped identifier) don't fit SOP documents, which cite by
document name and heading instead, so the two return different shapes,
not just different index names.
"""

from __future__ import annotations

import time
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import TransportError
from opentelemetry.trace import Span
from pydantic import BaseModel

from canopica_ai.common.observability import traced_retrieval_call
from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.retrieval import embed_text

# Same constants, same reasoning as policy_intelligence.retrieval's own
# _RETRYABLE_SEARCH_STATUS/_MAX_SEARCH_ATTEMPTS/_RETRY_BACKOFF_SECONDS --
# ml-commons' circuit breaker is a property of the shared OpenSearch
# cluster and reranker deployment, not of which index is being searched.
_RETRYABLE_SEARCH_STATUS = 429
_MAX_SEARCH_ATTEMPTS = 6
_RETRY_BACKOFF_SECONDS = 3.0


class SopRetrievedChunk(BaseModel):
    document: str
    heading: str
    text: str
    chunk_id: str
    score: float


def _client(settings: Settings) -> OpenSearch:
    return OpenSearch(hosts=[settings.opensearch_url])


def _search_with_backpressure_retry(
    client: OpenSearch, body: dict[str, Any], settings: Settings, span: Span
) -> dict[str, Any]:
    for attempt in range(_MAX_SEARCH_ATTEMPTS):
        try:
            response: dict[str, Any] = client.search(
                index=settings.sop_corpus_index,
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
) -> list[SopRetrievedChunk]:
    settings = settings or Settings()
    client = client or _client(settings)

    with traced_retrieval_call(index=settings.sop_corpus_index, top_k=top_k) as span:
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
            SopRetrievedChunk(
                document=hit["_source"]["document"],
                heading=hit["_source"]["heading"],
                text=hit["_source"]["text"],
                chunk_id=hit["_id"],
                score=hit["_score"],
            )
            for hit in response["hits"]["hits"]
        ]
        span.set_attribute("canopica.retrieval.chunk_count", len(chunks))
        return chunks
