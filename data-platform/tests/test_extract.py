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
def test_extract_appends_rather_than_overwrites(
    seeded_operational_dsn: str, tmp_path: Path
) -> None:
    extract_to_bronze(seeded_operational_dsn, tmp_path, ["person"])
    extract_to_bronze(seeded_operational_dsn, tmp_path, ["person"])

    dt = DeltaTable(str(tmp_path / "person"))
    assert dt.version() == 1  # two commits, second is version 1
    assert dt.to_pyarrow_table().num_rows == 2 * SEEDED_PERSON_COUNT
