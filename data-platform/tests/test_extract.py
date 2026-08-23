"""Integration tests for the bronze ingestion layer -- needs a real Postgres
instance with real operational rows, since the point is proving extraction
lands actual table bytes plus ingest metadata, not a mocked shape."""

from pathlib import Path

import pytest
from deltalake import DeltaTable

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
