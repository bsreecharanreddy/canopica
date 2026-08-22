"""End-to-end: intake -> determination -> audit -> warehouse -> mart, against
the real Compose stack (`make up`) with no mocks anywhere in the chain. The
point of the final assertion isn't "does the pipeline run" -- it's that the
dollar amount a report shows is the exact number the rules engine decided,
not a re-derivation that happens to look similar.

Needs the full stack already built and running (`make up`), same
precondition as test_stack_smoke.py -- CI's `e2e` job brings it up itself; a
local run needs that done first.
"""

from __future__ import annotations

import os
import random
import subprocess
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest

from canopica_data.audit.verify_chain import verify_chain
from canopica_data.config import Settings
from canopica_data.ingestion.extract import ALL_TABLES, extract_to_bronze
from canopica_data.serving.materialize import materialize_gold
from canopica_data.synthetic.generator import generate_households
from canopica_data.synthetic.loader import post_households

DATA_PLATFORM_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = DATA_PLATFORM_ROOT / "dbt" / "canopica_warehouse"

# Mirrors the DMN model's own reasonCode literal expression
# (rules-engine/src/main/resources/dmn/snap-eligibility.dmn) -- grows if that
# model ever adds another branch.
REASON_CODES = {
    "ELIGIBLE",
    "GROSS_INCOME_EXCEEDS_LIMIT",
    "NET_INCOME_EXCEEDS_LIMIT",
    "ZERO_BENEFIT_AMOUNT",
}

# Every SNAP policy_parameter_set version seeded so far
# (V4__seed_snap_parameters.sql) -- grows whenever a new fiscal year's
# figures are seeded. Not asserting a single hardcoded version: which one
# actually applies depends on "today" against each set's effective_from/
# effective_to, and FY2025 already closed (effective_to 2025-09-30) by the
# time this test runs against a real clock.
KNOWN_SNAP_PARAMETER_VERSIONS = {"SNAP-FY2025", "SNAP-FY2026"}


@dataclass(frozen=True)
class StackFixture:
    """Points at the real `make up` Compose stack, not Testcontainers --
    this test proves the actual deployed services agree end to end, not a
    hand-assembled approximation of them."""

    api_url: str
    operational_dsn: str
    serving_dsn: str
    bronze_root: Path
    duckdb_path: Path


@pytest.fixture
def stack(tmp_path: Path) -> StackFixture:
    settings = Settings()
    return StackFixture(
        api_url="http://localhost:8080",
        operational_dsn=settings.operational_dsn,
        serving_dsn=settings.serving_dsn,
        bronze_root=tmp_path / "bronze",
        duckdb_path=tmp_path / "canopica.duckdb",
    )


def _run_determination(
    api_url: str, program_request_id: uuid.UUID, *, as_of: date, benefit_month: date
) -> dict[str, Any]:
    response = httpx.post(
        f"{api_url}/api/program-requests/{program_request_id}/determinations",
        json={"asOfDate": as_of.isoformat(), "benefitMonth": benefit_month.isoformat()},
        headers={"X-Canopica-Role": "WORKER"},
        timeout=30.0,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


def _get_trace(api_url: str, determination_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"{api_url}/api/determinations/{determination_id}/trace",
        headers={"X-Canopica-Role": "WORKER"},
        timeout=30.0,
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result


def _random_benefit_month() -> date:
    """A benefit_month unlikely to collide with any earlier test run's row
    in the same (benefit_month, outcome, reason_code, policy_parameter_version)
    mart group -- see the test's own docstring for why that group has to
    stay unique per run. Decoupled from `as_of` on purpose: the real system
    doesn't tie benefit_month to as_of either (DetermineRequest carries them
    as two independent fields), so picking a benefit_month nowhere near
    "today" doesn't affect fact assembly or parameter-version resolution,
    both of which are driven by `as_of` alone."""
    year = date.today().year + random.randint(0, 50)
    month = random.randint(1, 12)
    return date(year, month, 1)


def _run_dbt_build(warehouse_root: Path, duckdb_path: Path) -> None:
    result = subprocess.run(
        [
            "dbt",
            "build",
            "--project-dir",
            str(DBT_PROJECT_DIR),
            "--profiles-dir",
            str(DBT_PROJECT_DIR),
            "--target",
            "local",
        ],
        cwd=DATA_PLATFORM_ROOT,
        env={
            **os.environ,
            "CANOPICA_WAREHOUSE_ROOT": str(warehouse_root),
            "CANOPICA_DUCKDB_PATH": str(duckdb_path),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.e2e
def test_intake_through_determination_audit_warehouse_and_mart(stack: StackFixture) -> None:
    """Repeatable against a live, already-populated Postgres, not just a
    fresh one -- found the hard way running this test twice in a row
    against the same `make up` stack: with a fixed benefit_month, the second
    run's row landed in the same (benefit_month, outcome, reason_code,
    policy_parameter_version) group the mart already had one row in from
    the first run, and `determination_count == 1` failed with `2 == 1`.
    Fixed by giving each run its own random benefit_month (see
    `_random_benefit_month`) rather than requiring a `make down && make up`
    between runs.
    """
    # 1. Intake -- a known household, through the real API.
    household = generate_households(1, seed=1234)[0]
    ids = post_households([household], stack.api_url)[0]

    # 2. Determination -- through the real API, as a worker. `as_of` must be
    #    on/after today: FactAssembler (portal) only sees household_member
    #    rows whose effective_from -- set to the real submission date by
    #    IntakeService -- is <= as_of.
    as_of = date.today()
    benefit_month = _random_benefit_month()
    determination = _run_determination(
        stack.api_url, ids.program_request_id, as_of=as_of, benefit_month=benefit_month
    )
    assert determination["policyParameterVersion"] in KNOWN_SNAP_PARAMETER_VERSIONS
    assert determination["reasonCode"] in REASON_CODES

    # 3. Trace -- persisted, complete, and matching the model that ran.
    trace = _get_trace(stack.api_url, determination["determinationId"])
    assert "Excess Shelter Deduction" in trace["decisionResults"]
    assert len(trace["dmnModelHash"]) == 64

    # 4. Audit -- the chain covers the new events (APPLICATION_SUBMITTED,
    #    DETERMINATION_MADE) and still verifies.
    chain = verify_chain(stack.operational_dsn)
    assert chain.ok
    assert chain.rows_checked >= 2

    # 5. Warehouse -- bronze, silver, gold all rebuild from the live database.
    extract_to_bronze(stack.operational_dsn, stack.bronze_root, list(ALL_TABLES))
    _run_dbt_build(stack.bronze_root.parent, stack.duckdb_path)

    # 6. Mart -- the determination is visible, with the right money, under
    #    the parameter version that produced it. This is the assertion that
    #    matters: the number a report shows is the same number the rules
    #    engine decided, not a re-derivation that happens to look similar.
    materialize_gold(duckdb_path=stack.duckdb_path, serving_dsn=stack.serving_dsn)
    with psycopg.connect(stack.serving_dsn) as conn:
        row = conn.execute(
            """
            select determination_count, total_benefit_amount, policy_parameter_version
            from reporting.mart_determination_outcomes
            where benefit_month = %s
            """,
            (benefit_month,),
        ).fetchone()
    assert row is not None
    determination_count, total_benefit_amount, policy_parameter_version = row
    assert determination_count == 1
    assert policy_parameter_version == determination["policyParameterVersion"]
    assert total_benefit_amount == Decimal(str(determination["benefitAmount"]))
