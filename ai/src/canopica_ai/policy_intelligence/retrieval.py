"""Hybrid (BM25 + k-NN) retrieval over the CFR corpus, fused by RRF and
reranked by a cross-encoder -- the sole read path every later Policy
Intelligence feature (Task 2's Q&A service, Task 7's eval harness) calls.
Neither talks to OpenSearch directly; this module is the only one that does.
"""

from __future__ import annotations

import httpx
from opensearchpy import OpenSearch
from pydantic import BaseModel

from canopica_ai.common.observability import traced_retrieval_call
from canopica_ai.config import Settings


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

        response = client.search(
            index=settings.cfr_corpus_index,
            body=body,
            params={"search_pipeline": settings.cfr_search_pipeline},
        )

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
