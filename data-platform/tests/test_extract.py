"""Integration tests for the bronze ingestion layer -- needs a real Postgres
instance with real operational rows, since the point is proving extraction
lands actual table bytes plus ingest metadata, not a mocked shape."""

import shutil
from pathlib import Path

import pytest
from deltalake import DeltaTable, write_deltalake

from canopica_data.ingestion.extract import extract_to_bronze

# Must match conftest.py's seeded_operational_dsn fixture, which seeds this
# many person rows per invocation.
SEEDED_PERSON_COUNT = 3


@pytest.mark.integration
def test_extract_lands_every_row_with_ingest_metadata(
    seeded_operational_dsn: str, tmp_path: Path
) -> None:
    counts = extract_to_bronze(
        seeded_operational_dsn, tmp_path, ["person", "eligibility_determination"]
    )

    assert counts["person"] == SEEDED_PERSON_COUNT
    assert counts["eligibility_determination"] == 1

    table = DeltaTable(str(tmp_path / "eligibility_determination")).to_pyarrow_table()
    assert {"_ingested_at", "_source_table", "_batch_id"} <= set(table.column_names)


@pytest.mark.integration
def test_extract_lands_phase_1b_widened_tables(
    seeded_operational_dsn: str, tmp_path: Path
) -> None:
    """Task 5 widened bronze past Phase 1a's narrow seven -- proves each of
    the new tables lands the one seeded row conftest.py's
    seeded_operational_dsn now inserts, not just that the query doesn't
    error against an empty table."""
    counts = extract_to_bronze(
        seeded_operational_dsn,
        tmp_path,
        ["application", "worker", "case_assignment", "verification",
         "verification_response", "benefit_month", "audit_event"],
    )

    assert counts["application"] == 1
    assert counts["worker"] == 1
    assert counts["case_assignment"] == 1
    assert counts["verification"] == 1
    assert counts["verification_response"] == 1
    assert counts["benefit_month"] == 1
    assert counts["audit_event"] == 1


@pytest.mark.integration
def test_extract_appends_rather_than_overwrites(
    seeded_operational_dsn: str, tmp_path: Path
) -> None:
    extract_to_bronze(seeded_operational_dsn, tmp_path, ["person"])
    extract_to_bronze(seeded_operational_dsn, tmp_path, ["person"])

    dt = DeltaTable(str(tmp_path / "person"))
    assert dt.version() == 1  # two commits, second is version 1
    assert dt.to_pyarrow_table().num_rows == 2 * SEEDED_PERSON_COUNT


@pytest.mark.integration
def test_extract_tolerates_a_source_table_gaining_a_column(
    seeded_operational_dsn: str, tmp_path: Path
) -> None:
    """A real bug hit live (2026-08-23): Task 2's migration added
    `person.keycloak_subject`, and the next Airflow run of this exact
    function failed with deltalake's `SchemaMismatchError` trying to append
    a 12-column frame onto bronze/person's existing 11-column history.
    `select *` (this module's own docstring: "no reshaping") means any
    bronze-covered table gaining a column is normal, expected schema
    evolution, not a reason every later extract run should start failing --
    simulated here by writing a copy of a real extract with the column
    stripped back out, standing in for "bronze data written before this
    migration existed", then extracting again for real."""
    extract_to_bronze(seeded_operational_dsn, tmp_path, ["person"])
    narrowed = DeltaTable(str(tmp_path / "person")).to_pyarrow_table().drop_columns(
        ["keycloak_subject"]
    )
    shutil.rmtree(tmp_path / "person")
    write_deltalake(str(tmp_path / "person"), narrowed, mode="append")

    counts = extract_to_bronze(seeded_operational_dsn, tmp_path, ["person"])

    assert counts["person"] == SEEDED_PERSON_COUNT
    table = DeltaTable(str(tmp_path / "person")).to_pyarrow_table()
    assert table.num_rows == 2 * SEEDED_PERSON_COUNT
    assert "keycloak_subject" in table.column_names
