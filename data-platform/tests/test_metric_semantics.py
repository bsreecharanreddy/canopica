"""Task 4's own coverage for the MetricFlow semantic layer: proves the
manifest covers every gold mart and that a real `mf query` against a real
dbt-built warehouse returns real, correct numbers -- not just that the YAML
parses. Same fixture pattern as test_mart_processing_timeliness.py.

Filed under data-platform/tests/, not ai/tests/ as the Task 4 plan's own
file list said -- the fixture pattern it names (Testcontainers Postgres,
dbt CLI, DBT_PROJECT_DIR) only exists in data-platform's own conftest.py
and dependency set, which ai/ does not have. Corrected here the same way
Task 3's plan corrections were: found while writing the code, not by
re-reading the plan.
"""

from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from canopica_data.governance.tokenize import tokenize_person_names
from canopica_data.ingestion.extract import ALL_TABLES, extract_to_bronze

DATA_PLATFORM_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = DATA_PLATFORM_ROOT / "dbt" / "canopica_warehouse"
SEMANTIC_MODELS_YML = DBT_PROJECT_DIR / "models" / "semantic" / "semantic_models.yml"
GOLD_YML = DBT_PROJECT_DIR / "models" / "gold" / "gold.yml"
TEST_ENCRYPTION_KEY = "test-pii-vault-key"


def test_every_gold_mart_has_a_semantic_model() -> None:
    gold_marts = {m["name"] for m in yaml.safe_load(GOLD_YML.read_text())["models"]}

    semantic_models = yaml.safe_load(SEMANTIC_MODELS_YML.read_text())["semantic_models"]
    # model: is always written as "ref('mart_x')" -- strip the ref() wrapper
    # rather than eval it, since this is a static YAML/text check, not a
    # dbt-context test.
    modeled_marts = {sm["model"].removeprefix("ref('").removesuffix("')") for sm in semantic_models}

    assert modeled_marts == gold_marts


@pytest.mark.integration
def test_mf_query_returns_the_correct_avg_processing_days(
    seeded_timeliness_dsn: str, tmp_path: Path
) -> None:
    warehouse_root = tmp_path
    duckdb_path = tmp_path / "canopica.duckdb"
    extract_to_bronze(seeded_timeliness_dsn, warehouse_root / "bronze", list(ALL_TABLES))
    tokenize_person_names(seeded_timeliness_dsn, warehouse_root / "bronze", TEST_ENCRYPTION_KEY)

    env = {
        **os.environ,
        "CANOPICA_WAREHOUSE_ROOT": str(warehouse_root),
        "CANOPICA_DUCKDB_PATH": str(duckdb_path),
    }

    build = subprocess.run(
        [
            "dbt", "build",
            "--project-dir", str(DBT_PROJECT_DIR),
            "--profiles-dir", str(DBT_PROJECT_DIR),
            "--target", "local",
        ],
        cwd=DATA_PLATFORM_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr

    validate = subprocess.run(
        ["mf", "validate-configs"],
        cwd=DBT_PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr

    csv_path = tmp_path / "avg_processing_days.csv"
    query = subprocess.run(
        [
            "mf", "query",
            "--metrics", "avg_processing_days",
            "--group-by", "determination__is_expedited",
            "--order", "determination__is_expedited",
            "--csv", str(csv_path),
        ],
        cwd=DBT_PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert query.returncode == 0, query.stdout + query.stderr

    with csv_path.open() as f:
        rows = list(csv.DictReader(f))

    # seeded_timeliness_dsn's four scenarios: expedited 3/10 days elapsed
    # (avg 6.5), standard 15/35 days elapsed (avg 25.0) -- same fixture
    # test_mart_processing_timeliness.py already proves the underlying mart
    # gets right; this proves MetricFlow's compiled query aggregates it
    # correctly on top.
    by_expedited = {
        row["determination__is_expedited"]: float(row["avg_processing_days"]) for row in rows
    }
    assert by_expedited == {"True": 6.5, "False": 25.0}
