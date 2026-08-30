"""Shared pytest fixtures: a real pgmq-enabled Postgres via Testcontainers
-- same pattern data-platform/tests/conftest.py already uses for its own
integration tests, not `ai/`'s "assume `make up` already ran" e2e
convention. pgmq needs a specific bundled image
(`ghcr.io/pgmq/pg18-pgmq`), so a self-contained, ephemeral container per
test session is the better fit than depending on the local Compose
stack's own `postgres` service already being on the right image."""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from canopica_worker.config import Settings

# Same tag infra/docker-compose.yml pins for the real stack -- one
# version, one place each is decided, this file reads the compose file's
# own comment for why rather than re-deriving it.
_PGMQ_IMAGE = "ghcr.io/pgmq/pg18-pgmq:v1.10.0"

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "api" / "src" / "main" / "resources" / "db" / "migration"
)


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


@pytest.fixture(scope="session")
def migrated_settings(settings: Settings, _postgres_container: PostgresContainer) -> Settings:
    """`settings` plus the real API Flyway migrations and all three real
    pgmq queues -- for test files (test_document_intake_consumer.py, test_
    correspondence_consumer.py, test_fraud_scoring_consumer.py) that need
    `document`/`program_request`/`verification`/`audit_event`/`notice`/
    `fraud_risk_score` to actually exist, not just pgmq's own tables. Same
    `flyway/flyway` Docker-CLI pattern data-
    platform/tests/conftest.py's own `migrated_dsn` fixture already
    established for the identical reason -- reused here, run against the
    same Testcontainers instance `settings` already provisioned pgmq onto,
    rather than a second container."""
    host_port = _postgres_container.get_exposed_port(5432)
    jdbc_url = f"jdbc:postgresql://host.docker.internal:{host_port}/canopica_operational"
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--add-host=host.docker.internal:host-gateway",
            "-v",
            f"{MIGRATIONS_DIR}:/flyway/sql:ro",
            "flyway/flyway:11-alpine",
            f"-url={jdbc_url}",
            "-user=canopica_app",
            "-password=canopica_app",
            "-connectRetries=30",
            "-placeholders.app_role=canopica_app",
            "migrate",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute("select pgmq.create(%s)", (settings.document_intake_queue,))
        cur.execute("select pgmq.create(%s)", (settings.correspondence_dispatch_queue,))
        cur.execute("select pgmq.create(%s)", (settings.fraud_scoring_queue,))
    return settings


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
