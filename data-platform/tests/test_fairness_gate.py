"""Phase 4 Task 1's own coverage for mart_fairness_audit and its CI gate
(tests/gate_no_disparate_impact.sql) -- proves the gate genuinely fires on a
real induced disparity, and genuinely withholds judgment on a slice too
small to say anything from, not just that the mart computes a number.
Mirrors test_mart_processing_timeliness.py's own real-dbt-build shape.
"""

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


def _run_dbt_build(warehouse_root: Path, duckdb_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "dbt", "build",
            "--project-dir", str(DBT_PROJECT_DIR),
            "--profiles-dir", str(DBT_PROJECT_DIR),
            "--target", "local",
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


@pytest.mark.integration
def test_gate_fires_on_a_real_disparate_impact_and_withholds_on_a_tiny_slice(
    seeded_fairness_dsn: str, tmp_path: Path
) -> None:
    warehouse_root = tmp_path
    duckdb_path = tmp_path / "canopica.duckdb"
    extract_to_bronze(seeded_fairness_dsn, warehouse_root / "bronze", list(ALL_TABLES))
    tokenize_person_names(seeded_fairness_dsn, warehouse_root / "bronze", TEST_ENCRYPTION_KEY)

    # dbt build's own exit code IS the gate: this fixture's WHITE/BLACK_OR_AFRICAN_AMERICAN
    # disparity (0.9 vs 0.3 approval rate, both n=30) is exactly what
    # tests/gate_no_disparate_impact.sql exists to catch, so a green build here would mean the
    # gate is not actually wired into `dbt build` -- the opposite of what Task 1 Step 6 requires.
    result = _run_dbt_build(warehouse_root, duckdb_path)
    assert result.returncode != 0, (
        "gate_no_disparate_impact should have failed the build on this fixture's induced "
        "disparity, but the build succeeded:\n" + result.stdout + result.stderr
    )
    assert "gate_no_disparate_impact" in result.stdout

    # The mart itself still materialized before the test step ran (dbt build runs models before
    # tests) -- confirm the actual numbers, not just that *some* test failed.
    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        rows = con.execute(
            "select demographic_slice, total_count, favorable_count, selection_rate, "
            "disparate_impact_ratio, sample_size_adequate "
            "from main_gold.mart_fairness_audit "
            "where model = 'rules_engine' and demographic_axis = 'race' "
            "order by demographic_slice"
        ).fetchall()
    finally:
        con.close()

    by_slice = {r[0]: r for r in rows}

    white = by_slice["WHITE"]
    assert white[1] == 30  # total_count
    assert white[2] == 27  # favorable_count
    assert white[5] is True  # sample_size_adequate

    black = by_slice["BLACK_OR_AFRICAN_AMERICAN"]
    assert black[1] == 30
    assert black[2] == 9
    assert black[5] is True
    # 0.3 / 0.9 = 0.333... -- well under the four-fifths threshold, and the fixture's whole
    # point. WHITE (n=30, adequate) is the reference here, not the single-case ASIAN row (n=1,
    # rate 1.0), which mart_fairness_audit.sql's reference CTE deliberately excludes.
    assert black[4] == pytest.approx(0.3333, abs=0.001)
    assert black[4] < 0.8

    # The tiny ASIAN slice (n=1, eligible=True -- a ratio of 1.0, i.e. never itself the reason
    # the gate would fire) still has to be marked inadequate, proving the gate withholds
    # judgment on sample size rather than reacting to whatever ratio a single case happens to
    # produce.
    asian = by_slice["ASIAN"]
    assert asian[1] == 1
    assert asian[5] is False
