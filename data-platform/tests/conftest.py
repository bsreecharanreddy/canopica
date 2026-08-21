"""Shared pytest fixtures for data-platform integration tests.

Provides a real Postgres 16 instance (Testcontainers) with the portal's
actual Flyway migrations applied once per test session -- Python
integration tests exercise the same schema, triggers, and grants Java
does, not a hand-rolled approximation of them.

On this machine (Docker Desktop for macOS), Testcontainers' Ryuk reaper
container fails to start with "error while creating mount source path
...docker.sock: operation not supported" -- a known Docker-Desktop-on-macOS
socket-mount quirk, not a bug here. Run with
``TESTCONTAINERS_RYUK_DISABLED=true`` locally if hit; GitHub Actions'
Linux runners have not shown this issue.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2]
    / "portal"
    / "src"
    / "main"
    / "resources"
    / "db"
    / "migration"
)


@pytest.fixture(scope="session")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(
        "postgres:16-alpine", username="ies_app", password="ies_app", dbname="ies_operational"
    ) as container:
        yield container


@pytest.fixture(scope="session")
def migrated_dsn(_postgres_container: PostgresContainer) -> str:
    """A DSN for a Postgres instance with every V1-V6 migration applied.

    Runs the real portal Flyway migrations via the flyway CLI's own Docker
    image against the Testcontainers instance, over host.docker.internal --
    proving this suite exercises the actual migration files, not a copy of
    their SQL. ``host-gateway`` makes host.docker.internal resolve on Linux
    CI runners too, not just Docker Desktop.
    """
    host_port = _postgres_container.get_exposed_port(5432)
    jdbc_url = f"jdbc:postgresql://host.docker.internal:{host_port}/ies_operational"

    subprocess.run(
        [
            "docker", "run", "--rm",
            "--add-host=host.docker.internal:host-gateway",
            "-v", f"{MIGRATIONS_DIR}:/flyway/sql:ro",
            "flyway/flyway:11-alpine",
            f"-url={jdbc_url}",
            "-user=ies_app",
            "-password=ies_app",
            "-connectRetries=30",
            "-placeholders.app_role=ies_app",
            "migrate",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return f"postgresql://ies_app:ies_app@localhost:{host_port}/ies_operational"


@pytest.fixture
def seeded_audit_dsn(migrated_dsn: str) -> Iterator[str]:
    """migrated_dsn with a clean, freshly-seeded 5-row audit chain."""
    with psycopg.connect(migrated_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("truncate table audit_event restart identity")
        for i in range(5):
            cur.execute(
                "insert into audit_event (event_type, actor_id, subject_type, subject_id, payload) "
                "values ('CASE_VIEWED', %s, 'household', gen_random_uuid(), %s::jsonb)",
                (f"worker-{i}", f'{{"seq": {i}}}'),
            )
    yield migrated_dsn


@pytest.fixture
def as_superuser(migrated_dsn: str) -> Callable[[str], None]:
    """Runs raw SQL as the container's bootstrap role, which the official
    Postgres image makes a superuser by default. Used only to prove
    ``verify_chain()`` detects tampering that no application-level control
    could have prevented in the first place -- that's the point of the
    test this fixture serves, not a gap in the fixture."""

    def run(sql: str) -> None:
        with psycopg.connect(migrated_dsn, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(sql)

    return run
