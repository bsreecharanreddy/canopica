"""Shared pytest fixtures for ai/'s e2e suite: a real OpenSearch + Ollama
(the Compose stack's own services, assumed already running via `make up`
-- not spun up fresh per test session, the same convention
data-platform/tests/test_observability.py and test_airflow_dag.py already
use for heavy Compose-only services Testcontainers can't reasonably
stand in for, here because of Ollama's real multi-gigabyte model
downloads)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opensearchpy import OpenSearch

from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.corpus import search_pipeline
from canopica_ai.policy_intelligence.corpus.index import index_corpus


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def opensearch_client(settings: Settings) -> OpenSearch:
    return OpenSearch(hosts=[settings.opensearch_url])


@pytest.fixture(scope="session")
def indexed_corpus(settings: Settings, opensearch_client: OpenSearch) -> Iterator[Settings]:
    """Indexes the real corpus and provisions the real hybrid search
    pipeline against the live stack once per test session -- both are
    idempotent (index.py deletes/recreates; search_pipeline.py
    checks-before-creates), so this is safe to run unconditionally rather
    than assuming a human already ran `make pipeline`-equivalent setup."""
    index_corpus(opensearch_client, settings)
    search_pipeline.setup(opensearch_client, settings)
    yield settings
