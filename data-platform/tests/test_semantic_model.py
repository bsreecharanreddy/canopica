"""Parses the TMDL semantic model as plain text and checks it against the
gold mart's own dbt contract (gold.yml) -- cheap, but it means the semantic
model cannot silently drift from the mart it describes without a test
failing here first."""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE_TMDL = (
    REPO_ROOT / "reporting" / "semantic-model" / "tables" / "mart_determination_outcomes.tmdl"
)
GOLD_YML = REPO_ROOT / "data-platform" / "dbt" / "ies_warehouse" / "models" / "gold" / "gold.yml"

REQUIRED_MEASURES = {"Determinations", "Eligible Rate", "Average Benefit"}

COLUMN_RE = re.compile(r"^\tcolumn (\w+)$", re.MULTILINE)
MEASURE_RE = re.compile(r"^\tmeasure '([^']+)' =", re.MULTILINE)


def _gold_mart_columns() -> list[str]:
    models = yaml.safe_load(GOLD_YML.read_text())["models"]
    mart = next(m for m in models if m["name"] == "mart_determination_outcomes")
    return [c["name"] for c in mart["columns"]]


def test_every_gold_mart_column_is_declared_exactly_once() -> None:
    tmdl_text = TABLE_TMDL.read_text()
    declared_columns = COLUMN_RE.findall(tmdl_text)

    for column in _gold_mart_columns():
        assert declared_columns.count(column) == 1, (
            f"{column!r} should appear exactly once in the TMDL table, "
            f"found {declared_columns.count(column)}"
        )

    # And nothing declared here that the mart doesn't actually have --
    # the other direction of drift.
    assert set(declared_columns) == set(_gold_mart_columns())


def test_all_three_measures_are_defined() -> None:
    tmdl_text = TABLE_TMDL.read_text()
    declared_measures = set(MEASURE_RE.findall(tmdl_text))

    assert declared_measures == REQUIRED_MEASURES
