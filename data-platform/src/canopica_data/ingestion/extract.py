"""Lands operational Postgres tables as append-only Delta tables -- bronze,
no reshaping (roadmap §3.4.2). Silver deduplicates on natural key and the
latest ``_ingested_at``, which is why duplicates across batches here are
expected, not a bug.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from deltalake import write_deltalake

# The bronze/silver/gold shape this task establishes for Phase 1b to widen
# (roadmap §3.4.2's full table list) -- these seven are what the operational
# schema has through Task 9 and what dbt's sources.yml reads.
ALL_TABLES = (
    "person",
    "household",
    "household_member",
    "program_request",
    "eligibility_determination",
    "policy_parameter_set",
    "policy_parameter",
)


def extract_to_bronze(
    dsn: str,
    bronze_root: Path,
    tables: Sequence[str],
    *,
    batch_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Land each operational table as an append-only Delta table under
    ``bronze_root``. Returns {table_name: rows_written}."""
    resolved_batch_id = str(batch_id or uuid.uuid4())
    ingested_at = datetime.now(UTC)
    counts: dict[str, int] = {}

    for table in tables:
        # table name always comes from ALL_TABLES, never user input
        query = f"select * from {table}"
        frame = pl.read_database_uri(query=query, uri=dsn)
        frame = frame.with_columns(
            pl.lit(ingested_at).alias("_ingested_at"),
            pl.lit(table).alias("_source_table"),
            pl.lit(resolved_batch_id).alias("_batch_id"),
        )
        write_deltalake(str(bronze_root / table), frame.to_arrow(), mode="append")
        counts[table] = frame.height

    return counts
