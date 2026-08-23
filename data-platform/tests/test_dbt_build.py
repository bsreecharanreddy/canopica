"""Shells out to the real dbt CLI against a fixture warehouse -- proves the
bronze -> silver -> gold pipeline actually builds and every test (including
no_pii_in_gold) passes, not just that the SQL parses."""

import os
import subprocess
from pathlib import Path

import duckdb
import pytest

from ies_data.ingestion.extract import ALL_TABLES, extract_to_bronze

DATA_PLATFORM_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = DATA_PLATFORM_ROOT / "dbt" / "ies_warehouse"


@pytest.mark.integration
def test_dbt_build_produces_the_gold_mart(seeded_operational_dsn: str, tmp_path: Path) -> None:
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

    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        row_count = con.execute(
            "select count(*) from main_gold.mart_determination_outcomes"
        ).fetchone()
        assert row_count is not None
        assert row_count[0] == 1

        # Task 5's three new marts -- each seeded to produce exactly one row
        # by conftest.py's seeded_operational_dsn.
        for mart in ("mart_worker_caseload", "mart_access_review", "mart_payment_accuracy"):
            mart_row_count = con.execute(f"select count(*) from main_gold.{mart}").fetchone()
            assert mart_row_count is not None
            assert mart_row_count[0] == 1, mart
    finally:
        con.close()
