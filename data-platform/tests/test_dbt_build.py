"""Shells out to the real dbt CLI against a fixture warehouse -- proves the
bronze -> silver -> gold pipeline actually builds and every test (including
no_pii_in_gold) passes, not just that the SQL parses."""

import os
import subprocess
from pathlib import Path

import duckdb
import pytest

from ies_data.governance.tokenize import tokenize_person_names
from ies_data.ingestion.extract import ALL_TABLES, extract_to_bronze

DATA_PLATFORM_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = DATA_PLATFORM_ROOT / "dbt" / "ies_warehouse"
TEST_ENCRYPTION_KEY = "test-pii-vault-key"


@pytest.mark.integration
def test_dbt_build_produces_the_gold_mart(seeded_operational_dsn: str, tmp_path: Path) -> None:
    warehouse_root = tmp_path
    duckdb_path = tmp_path / "ies.duckdb"
    extract_to_bronze(seeded_operational_dsn, warehouse_root / "bronze", list(ALL_TABLES))
    # dim_person.sql (Task 7) joins against this bronze landing -- must run
    # before dbt build, same as extract_to_bronze above.
    tokenize_person_names(seeded_operational_dsn, warehouse_root / "bronze", TEST_ENCRYPTION_KEY)

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

        # Task 5's three new marts plus Task 6's mart_processing_timeliness --
        # each seeded to produce exactly one row by conftest.py's
        # seeded_operational_dsn. mart_processing_timeliness's own real
        # expedited/late coverage lives in test_mart_processing_timeliness.py,
        # against a dedicated fixture -- this assertion only proves the model
        # itself builds and produces a row, same as its three siblings here.
        for mart in ("mart_worker_caseload", "mart_access_review", "mart_payment_accuracy",
                     "mart_processing_timeliness"):
            mart_row_count = con.execute(f"select count(*) from main_gold.{mart}").fetchone()
            assert mart_row_count is not None
            assert mart_row_count[0] == 1, mart
    finally:
        con.close()
