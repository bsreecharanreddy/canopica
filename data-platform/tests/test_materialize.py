"""Builds a real warehouse (bronze -> dbt gold) and materializes it into a
real serving Postgres database via DuckDB's postgres extension -- proves the
serving copy is the warehouse's own numbers, not a re-aggregation."""

import os
import subprocess
from pathlib import Path

import duckdb
import psycopg
import pytest

from ies_data.ingestion.extract import ALL_TABLES, extract_to_bronze
from ies_data.serving.materialize import materialize_gold

DATA_PLATFORM_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = DATA_PLATFORM_ROOT / "dbt" / "ies_warehouse"


@pytest.mark.integration
def test_gold_mart_materializes_into_the_serving_database(
    seeded_operational_dsn: str, serving_dsn: str, tmp_path: Path
) -> None:
    warehouse_root = tmp_path
    duckdb_path = tmp_path / "ies.duckdb"
    extract_to_bronze(seeded_operational_dsn, warehouse_root / "bronze", list(ALL_TABLES))

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
            "IES_WAREHOUSE_ROOT": str(warehouse_root),
            "IES_DUCKDB_PATH": str(duckdb_path),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    counts = materialize_gold(duckdb_path=duckdb_path, serving_dsn=serving_dsn)
    assert counts["mart_determination_outcomes"] == 1
    # Task 5's three new marts plus Task 6's, materialized the same way.
    assert counts["mart_worker_caseload"] == 1
    assert counts["mart_access_review"] == 1
    assert counts["mart_payment_accuracy"] == 1
    assert counts["mart_processing_timeliness"] == 1

    with psycopg.connect(serving_dsn) as conn:
        gold_total = conn.execute(
            "select sum(total_benefit_amount) from reporting.mart_determination_outcomes"
        ).fetchone()
    assert gold_total is not None

    duck_con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        duck_total = duck_con.execute(
            "select sum(total_benefit_amount) from main_gold.mart_determination_outcomes"
        ).fetchone()
    finally:
        duck_con.close()
    assert duck_total is not None

    assert gold_total[0] == duck_total[0]  # the serving copy is not a re-aggregation


@pytest.mark.integration
def test_materialize_is_rerunnable(
    seeded_operational_dsn: str, serving_dsn: str, tmp_path: Path
) -> None:
    """A second pipeline run (e.g. `make pipeline` re-run in dev) must
    replace the mart wholesale, not fail or double it -- Phase 1a's gold
    marts are rebuilt wholesale each run (see materialize.py's docstring)."""
    warehouse_root = tmp_path
    duckdb_path = tmp_path / "ies.duckdb"
    extract_to_bronze(seeded_operational_dsn, warehouse_root / "bronze", list(ALL_TABLES))
    subprocess.run(
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
            "IES_WAREHOUSE_ROOT": str(warehouse_root),
            "IES_DUCKDB_PATH": str(duckdb_path),
        },
        capture_output=True,
        text=True,
        check=True,
    )

    materialize_gold(duckdb_path=duckdb_path, serving_dsn=serving_dsn)
    counts = materialize_gold(duckdb_path=duckdb_path, serving_dsn=serving_dsn)

    assert counts["mart_determination_outcomes"] == 1
    assert counts["mart_worker_caseload"] == 1
    assert counts["mart_access_review"] == 1
    assert counts["mart_payment_accuracy"] == 1
    assert counts["mart_processing_timeliness"] == 1
