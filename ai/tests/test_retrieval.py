"""Needs the real OpenSearch + Ollama from `make up` (see conftest.py's
indexed_corpus fixture) -- proves hybrid_search() against the live,
RRF-fused, cross-encoder-reranked pipeline, not a mocked search client."""

from __future__ import annotations

import pytest
from opensearchpy import OpenSearch

from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.corpus import search_pipeline
from canopica_ai.policy_intelligence.retrieval import RetrievedChunk, hybrid_search

pytestmark = pytest.mark.e2e


def test_hybrid_search_returns_gross_income_sections_near_the_top(indexed_corpus: Settings) -> None:
    results = hybrid_search("What is the gross income test for eligibility?", top_k=5)

    assert results
    assert all(isinstance(r, RetrievedChunk) for r in results)
    top_sections = {r.cfr_section for r in results[:3]}
    assert any(section.startswith("273.9(a)") for section in top_sections)


def test_reranking_actually_changes_result_order(
    indexed_corpus: Settings, opensearch_client: OpenSearch
) -> None:
    """Proves the rerank response processor is live, not a no-op, by
    comparing against a second pipeline that only does RRF fusion."""
    rrf_only_pipeline = "cfr-hybrid-rrf-only-test"
    search_pipeline.ensure_ml_commons_settings(opensearch_client)
    opensearch_client.transport.perform_request(
        "PUT",
        f"/_search/pipeline/{rrf_only_pipeline}",
        body={
            "phase_results_processors": [
                {
                    "score-ranker-processor": {
                        "combination": {"technique": "rrf", "rank_constant": 60}
                    }
                }
            ]
        },
    )

    query = "excess shelter deduction cap for households"
    with_rerank = hybrid_search(query, top_k=5, settings=indexed_corpus)
    rrf_only_settings = indexed_corpus.model_copy(update={"cfr_search_pipeline": rrf_only_pipeline})
    without_rerank = hybrid_search(query, top_k=5, settings=rrf_only_settings)

    assert [r.chunk_id for r in with_rerank] != [r.chunk_id for r in without_rerank]


def test_hybrid_search_respects_top_k(indexed_corpus: Settings) -> None:
    results = hybrid_search("categorical eligibility", top_k=2)

    assert len(results) <= 2
