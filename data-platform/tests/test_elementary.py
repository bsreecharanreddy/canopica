"""Data-quality anomaly detection (Phase 4 Task 9, design doc §2.7): proves
the Elementary dbt package is genuinely adopted, not just declared in
packages.yml -- a real `dbt build` against a deliberately-broken fixture
(a determination decided before its own application was submitted) fails
`tests/no_negative_processing_days.sql` for real, and Elementary's own
on-run-end hook captures that failure into `main.elementary_test_results`
with the exact shape `canopica_ai.data_quality.elementary_ingest` reads.

`main.elementary_test_results`'s real schema/location was itself verified
live during implementation (2026-08-30) -- see that module's own
docstring for what was checked and why the schema lands at `main`, not a
nested `elementary` one, and why this project's own `dbt_project.yml`
deliberately adds no on-run-end hook of its own (the package already
defines one; adding a second was tried and confirmed to double-execute
it).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import duckdb
import pytest

from canopica_data.governance.tokenize import tokenize_person_names
from canopica_data.ingestion.extract import ALL_TABLES, extract_to_bronze

DATA_PLATFORM_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = DATA_PLATFORM_ROOT / "dbt" / "canopica_warehouse"
TEST_ENCRYPTION_KEY = "test-pii-vault-key"


@pytest.mark.integration
def test_a_deliberately_broken_fixture_is_captured_by_elementary(
    seeded_data_quality_dsn: str, tmp_path: Path
) -> None:
    warehouse_root = tmp_path
    duckdb_path = tmp_path / "canopica.duckdb"
    extract_to_bronze(seeded_data_quality_dsn, warehouse_root / "bronze", list(ALL_TABLES))
    tokenize_person_names(seeded_data_quality_dsn, warehouse_root / "bronze", TEST_ENCRYPTION_KEY)

    env = {
        **os.environ,
        "CANOPICA_WAREHOUSE_ROOT": str(warehouse_root),
        "CANOPICA_DUCKDB_PATH": str(duckdb_path),
    }
    result = subprocess.run(
        ["dbt", "build", "--project-dir", str(DBT_PROJECT_DIR),
         "--profiles-dir", str(DBT_PROJECT_DIR), "--target", "local"],
        cwd=DATA_PLATFORM_ROOT, env=env, capture_output=True, text=True, check=False,
    )
    # A real, expected failure: the fixture's own negative-processing-days
    # determination trips no_negative_processing_days.sql on purpose.
    # returncode 1 is "tests failed" (dbt's own convention); anything else
    # (2+, a parse/runtime error) is a real bug in this test setup.
    assert result.returncode == 1, result.stdout + result.stderr
    assert "no_negative_processing_days" in result.stdout

    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        row = con.execute(
            "select table_name, test_type, status, test_results_query, invocation_id "
            "from main.elementary_test_results "
            "where test_unique_id = 'test.canopica_warehouse.no_negative_processing_days' "
            "and status = 'fail'"
        ).fetchone()
    finally:
        con.close()

    assert row is not None, "Elementary's own on-run-end hook never captured the induced failure"
    table_name, test_type, status, test_results_query, invocation_id = row
    assert table_name == "mart_processing_timeliness"
    assert test_type == "dbt_test"
    assert status == "fail"
    assert test_results_query is not None and "processing_days < 0" in test_results_query
    # non-empty -- canopica_ai.data_quality.cli's own --run-results scopes to this
    assert invocation_id
