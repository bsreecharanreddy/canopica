"""Shared pytest fixtures for data-platform integration tests.

Provides a real Postgres 16 instance (Testcontainers) with the API's
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
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

# The FY2025 policy_parameter_set id V4__seed_snap_parameters.sql seeds --
# reused so fixtures don't need to insert their own parameter set.
SNAP_FY2025_PARAMETER_SET_ID = "9f1c0e10-0000-4000-8000-000000000001"
SEEDED_PERSON_COUNT = 3

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2]
    / "api"
    / "src"
    / "main"
    / "resources"
    / "db"
    / "migration"
)


@pytest.fixture(scope="session")
def _postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(
        # 16-alpine -> 18-alpine (Phase 3 Task 1): kept in step with
        # infra/docker-compose.yml's own postgres service, which moved to a
        # pgmq-bundled Postgres 18 image so the worker's queues can exist.
        # Neither container here needs pgmq itself -- staying on the same
        # major version as the rest of the stack is the only reason.
        "postgres:18-alpine",
        username="canopica_app",
        password="canopica_app",
        dbname="canopica_operational",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def _serving_postgres_container() -> Iterator[PostgresContainer]:
    """A separate, unmigrated Postgres instance standing in for the serving
    database -- materialize_gold() creates its own `reporting` schema/tables,
    so no Flyway migrations belong here, unlike migrated_dsn's operational
    container."""
    with PostgresContainer(
        # 16-alpine -> 18-alpine (Phase 3 Task 1): kept in step with
        # infra/docker-compose.yml's own postgres service, which moved to a
        # pgmq-bundled Postgres 18 image so the worker's queues can exist.
        # Neither container here needs pgmq itself -- staying on the same
        # major version as the rest of the stack is the only reason.
        "postgres:18-alpine",
        username="canopica_app",
        password="canopica_app",
        dbname="canopica_serving",
    ) as container:
        yield container


@pytest.fixture
def serving_dsn(_serving_postgres_container: PostgresContainer) -> str:
    host_port = _serving_postgres_container.get_exposed_port(5432)
    return f"postgresql://canopica_app:canopica_app@localhost:{host_port}/canopica_serving"


@pytest.fixture(scope="session")
def migrated_dsn(_postgres_container: PostgresContainer) -> str:
    """A DSN for a Postgres instance with every V1-V6 migration applied.

    Runs the real API Flyway migrations via the flyway CLI's own Docker
    image against the Testcontainers instance, over host.docker.internal --
    proving this suite exercises the actual migration files, not a copy of
    their SQL. ``host-gateway`` makes host.docker.internal resolve on Linux
    CI runners too, not just Docker Desktop.
    """
    host_port = _postgres_container.get_exposed_port(5432)
    jdbc_url = f"jdbc:postgresql://host.docker.internal:{host_port}/canopica_operational"

    subprocess.run(
        [
            "docker", "run", "--rm",
            "--add-host=host.docker.internal:host-gateway",
            "-v", f"{MIGRATIONS_DIR}:/flyway/sql:ro",
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

    return f"postgresql://canopica_app:canopica_app@localhost:{host_port}/canopica_operational"


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
def seeded_operational_dsn(migrated_dsn: str) -> Iterator[str]:
    """migrated_dsn with one realistic determination chain seeded directly via
    SQL. Extraction only needs real rows to land in the tables Task 10's
    bronze layer reads -- it does not need a real rules-engine run, so this
    bypasses the API/DMN path Tasks 5-9 exercise elsewhere and inserts
    straight into person/household/application/program_request/
    eligibility_determination/determination_trace. Reuses the FY2025
    policy_parameter_set V4's migration already seeded rather than inserting
    a second one.

    Phase 1b Task 5 widened this to also seed one row each of
    worker/case_assignment/verification/verification_response/benefit_month/
    audit_event, tied to the same household/program_request/worker identity
    (case_assignment.worker_id, audit_event.actor_id == worker.keycloak_
    subject) -- otherwise the new dim_worker/fct_verification/fct_benefit_
    month/fct_audit_event silver models and the mart_worker_caseload/
    mart_access_review gold marts would only ever be exercised against an
    empty table, which proves the SQL parses but not that a real join
    produces a real row.
    """
    person_ids = [str(uuid.uuid4()) for _ in range(SEEDED_PERSON_COUNT)]
    household_id = str(uuid.uuid4())
    application_id = str(uuid.uuid4())
    program_request_id = str(uuid.uuid4())
    determination_id = str(uuid.uuid4())
    worker_id = str(uuid.uuid4())
    worker_keycloak_subject = "fixture-worker-sub"
    verification_id = str(uuid.uuid4())

    with psycopg.connect(migrated_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "truncate table determination_trace, eligibility_determination, "
            "verification_response, verification, benefit_month, case_assignment, "
            "program_request, application, household_member, household, person, "
            "worker, audit_event "
            "restart identity cascade"
        )
        for i, person_id in enumerate(person_ids):
            cur.execute(
                "insert into person (id, first_name, last_name, date_of_birth, ssn_token, sex) "
                "values (%s, %s, 'Fixture', date '1990-01-01', %s, 'X')",
                (person_id, f"Person{i}", f"tok-{person_id}"),
            )
        cur.execute(
            "insert into household "
            "(id, head_person_id, county, address_line1, city, state, zip_code) "
            "values (%s, %s, 'Test County', '1 Main St', 'Testville', 'WY', '82001')",
            (household_id, person_ids[0]),
        )
        cur.execute(
            "insert into household_member "
            "(id, household_id, person_id, relationship, effective_from) "
            "values (%s, %s, %s, 'SELF', date '2026-01-01')",
            (str(uuid.uuid4()), household_id, person_ids[0]),
        )
        cur.execute(
            "insert into application (id, household_id, submitted_at, channel) "
            "values (%s, %s, now(), 'ONLINE')",
            (application_id, household_id),
        )
        cur.execute(
            "insert into program_request (id, application_id, program_code, status, requested_on) "
            "values (%s, %s, 'SNAP', 'DETERMINED', date '2026-01-01')",
            (program_request_id, application_id),
        )
        cur.execute(
            "insert into eligibility_determination "
            "(id, program_request_id, benefit_month, as_of_date, eligible, benefit_amount, "
            "reason_code, policy_parameter_set_id, policy_parameter_version, decided_by) "
            "values (%s, %s, date '2026-01-01', date '2026-01-01', true, 292, 'ELIGIBLE', "
            "%s, 'SNAP-FY2025', 'test-fixture')",
            (determination_id, program_request_id, SNAP_FY2025_PARAMETER_SET_ID),
        )
        cur.execute(
            "insert into determination_trace "
            "(id, determination_id, input_snapshot, decision_results, dmn_model_name, "
            "dmn_model_hash, engine_version) "
            "values (%s, %s, '{}'::jsonb, '{}'::jsonb, 'snap-eligibility', "
            "'test-hash', 'test-1.0')",
            (str(uuid.uuid4()), determination_id),
        )
        cur.execute(
            "insert into worker (id, full_name, email, role, keycloak_subject) "
            "values (%s, 'Fixture Worker', 'fixture.worker@example.gov', 'WORKER', %s)",
            (worker_id, worker_keycloak_subject),
        )
        cur.execute(
            "insert into case_assignment (id, household_id, worker_id, effective_from) "
            "values (%s, %s, %s, date '2026-01-01')",
            (str(uuid.uuid4()), household_id, worker_id),
        )
        cur.execute(
            "insert into verification (id, program_request_id, data_element, status, due_on) "
            "values (%s, %s, 'INCOME', 'RECEIVED', date '2026-01-15')",
            (verification_id, program_request_id),
        )
        cur.execute(
            "insert into verification_response (id, verification_id, outcome, raw_payload) "
            "values (%s, %s, 'MATCHES', '{}'::jsonb)",
            (str(uuid.uuid4()), verification_id),
        )
        cur.execute(
            "insert into benefit_month (id, program_request_id, benefit_month) "
            "values (%s, %s, date '2026-01-01')",
            (str(uuid.uuid4()), program_request_id),
        )
        cur.execute(
            "insert into audit_event (event_type, actor_id, subject_type, subject_id, payload) "
            "values ('CASE_VIEWED', %s, 'program_request', %s, %s::jsonb)",
            (worker_keycloak_subject, program_request_id, '{"in_assignment": true}'),
        )

    yield migrated_dsn


@pytest.fixture
def seeded_timeliness_dsn(migrated_dsn: str) -> Iterator[str]:
    """migrated_dsn with four determination chains seeded directly via SQL,
    one for each combination Task 6's mart_processing_timeliness plan step
    calls for: expedited-on-time, expedited-late, standard-on-time,
    standard-late. Separate from seeded_operational_dsn (which is fixed at
    exactly one row, relied on by every other dbt-build test's own row-count
    assertion) since this fixture's whole point is multiple rows with
    different is_expedited/timing combinations.
    """
    person_id = str(uuid.uuid4())
    household_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    scenarios = [
        # (is_expedited, submitted_at, decided_at) -- 3/10 days elapsed for the
        # expedited pair (standard is 7 days), 15/35 for the standard pair
        # (standard is 30 days).
        (True, now - timedelta(days=3), now),
        (True, now - timedelta(days=10), now),
        (False, now - timedelta(days=15), now),
        (False, now - timedelta(days=35), now),
    ]

    with psycopg.connect(migrated_dsn, autocommit=True) as conn, conn.cursor() as cur:
        # audit_event/worker/case_assignment/verification/verification_response/
        # benefit_month aren't written by this fixture, but still need
        # truncating: migrated_dsn's underlying container is a session-wide
        # singleton (only Flyway re-runs per call, idempotently, against the
        # same live tables), so a stale CASE_VIEWED row left behind by an
        # earlier test's own fixture (e.g. seeded_operational_dsn) can
        # otherwise reference a program_request_id this fixture's own
        # truncate just deleted -- a real orphaned-row failure caught by
        # mart_access_review's relationships test the first time this
        # fixture ran after Task 5's own audit_event-seeding fixture.
        cur.execute(
            "truncate table determination_trace, eligibility_determination, "
            "verification_response, verification, benefit_month, case_assignment, "
            "program_request, application, household_member, household, person, "
            "worker, audit_event "
            "restart identity cascade"
        )
        cur.execute(
            "insert into person (id, first_name, last_name, date_of_birth, ssn_token, sex) "
            "values (%s, 'Timeliness', 'Fixture', date '1990-01-01', %s, 'X')",
            (person_id, f"tok-{person_id}"),
        )
        cur.execute(
            "insert into household "
            "(id, head_person_id, county, address_line1, city, state, zip_code) "
            "values (%s, %s, 'Test County', '1 Main St', 'Testville', 'WY', '82001')",
            (household_id, person_id),
        )
        cur.execute(
            "insert into household_member "
            "(id, household_id, person_id, relationship, effective_from) "
            "values (%s, %s, %s, 'SELF', date '2026-01-01')",
            (str(uuid.uuid4()), household_id, person_id),
        )
        for is_expedited, submitted_at, decided_at in scenarios:
            application_id = str(uuid.uuid4())
            program_request_id = str(uuid.uuid4())
            cur.execute(
                "insert into application (id, household_id, submitted_at, channel) "
                "values (%s, %s, %s, 'ONLINE')",
                (application_id, household_id, submitted_at),
            )
            cur.execute(
                "insert into program_request "
                "(id, application_id, program_code, status, requested_on, is_expedited) "
                "values (%s, %s, 'SNAP', 'DETERMINED', %s, %s)",
                (program_request_id, application_id, submitted_at.date(), is_expedited),
            )
            cur.execute(
                "insert into eligibility_determination "
                "(id, program_request_id, benefit_month, as_of_date, eligible, benefit_amount, "
                "reason_code, policy_parameter_set_id, policy_parameter_version, "
                "decided_by, decided_at) "
                "values (%s, %s, date '2026-01-01', %s, true, 292, 'ELIGIBLE', "
                "%s, 'SNAP-FY2025', 'test-fixture', %s)",
                (str(uuid.uuid4()), program_request_id, decided_at.date(),
                 SNAP_FY2025_PARAMETER_SET_ID, decided_at),
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
