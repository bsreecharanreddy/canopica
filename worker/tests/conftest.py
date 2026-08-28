"""Shared pytest fixtures: a real pgmq-enabled Postgres via Testcontainers
-- same pattern data-platform/tests/conftest.py already uses for its own
integration tests, not `ai/`'s "assume `make up` already ran" e2e
convention. pgmq needs a specific bundled image
(`ghcr.io/pgmq/pg18-pgmq`), so a self-contained, ephemeral container per
test session is the better fit than depending on the local Compose
stack's own `postgres` service already being on the right image."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from canopica_worker.config import Settings

# Same tag infra/docker-compose.yml pins for the real stack -- one
# version, one place each is decided, this file reads the compose file's
# own comment for why rather than re-deriving it.
_PGMQ_IMAGE = "ghcr.io/pgmq/pg18-pgmq:v1.10.0"


@pytest.fixture(scope="session")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(
        _PGMQ_IMAGE, username="canopica_app", password="canopica_app", dbname="canopica_operational"
    ) as container:
        yield container


@pytest.fixture(scope="session")
def settings(_postgres_container: PostgresContainer) -> Settings:
    # Plain `postgresql://`, not testcontainers' own `get_connection_url()`
    # (which returns a SQLAlchemy-style `+psycopg2` URL psycopg3 doesn't
    # accept) -- same construction data-platform/tests/conftest.py already
    # uses for the identical reason.
    host_port = _postgres_container.get_exposed_port(5432)
    dsn = f"postgresql://canopica_app:canopica_app@localhost:{host_port}/canopica_operational"
    with psycopg.connect(dsn) as conn:
        conn.execute("create extension if not exists pgmq cascade")
    return Settings(operational_dsn=dsn)


@pytest.fixture
def test_queue(settings: Settings) -> Iterator[str]:
    """A uniquely-named queue, created before and dropped after each
    test."""
    queue_name = f"test_{uuid.uuid4().hex}"
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute("select pgmq.create(%s)", (queue_name,))
    yield queue_name
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute("select pgmq.drop_queue(%s)", (queue_name,))
