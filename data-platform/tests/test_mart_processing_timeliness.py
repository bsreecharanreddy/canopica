"""Task 6's own real coverage for mart_processing_timeliness -- Task 5 shipped
this mart's four siblings but deferred this one until is_expedited became
real. Proves the expedited-vs-standard and on-time-vs-late logic against a
real dbt build, not just that the SQL parses."""

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
def test_mart_processing_timeliness_flags_the_right_rows_as_late(
    seeded_timeliness_dsn: str, tmp_path: Path
) -> None:
    warehouse_root = tmp_path
    duckdb_path = tmp_path / "ies.duckdb"
    extract_to_bronze(seeded_timeliness_dsn, warehouse_root / "bronze", list(ALL_TABLES))
    # dim_person.sql (Task 7) joins against this bronze landing -- must run
    # before dbt build, same as extract_to_bronze above.
    tokenize_person_names(seeded_timeliness_dsn, warehouse_root / "bronze", TEST_ENCRYPTION_KEY)

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
        rows = con.execute(
            "select is_expedited, standard_days, missed_standard "
            "from main_gold.mart_processing_timeliness order by processing_days"
        ).fetchall()
    finally:
        con.close()

    # 3-day expedited (on time), 10-day expedited (late), 15-day standard
    # (on time), 35-day standard (late) -- matches conftest.py's
    # seeded_timeliness_dsn scenarios exactly, in ascending processing-day
    # order.
    assert rows == [
        (True, 7, False),
        (True, 7, True),
        (False, 30, False),
        (False, 30, True),
    ]
