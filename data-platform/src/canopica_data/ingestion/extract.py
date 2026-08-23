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

from canopica_data.observability.tracing import traced

# Phase 1a's narrow seven, widened here (Phase 1b Task 5) to the rest of
# roadmap §3.4.2's table list. `application` and `benefit_month` land too,
# even though the Task 5 plan's own parenthetical only named the other
# five -- fct_application and fct_benefit_month (design doc §3.4.2's silver
# list) need a bronze source that didn't otherwise exist; a plan gap filled
# during implementation, not scope creep.
ALL_TABLES = (
    "person",
    "household",
    "household_member",
    "application",
    "program_request",
    "eligibility_determination",
    "policy_parameter_set",
    "policy_parameter",
    "worker",
    "case_assignment",
    "verification",
    "verification_response",
    "benefit_month",
    "audit_event",
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
    with traced("extract"):
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
            # schema_mode="merge": bronze does "no reshaping" (module
            # docstring) of what a source table currently looks like, and a
            # source table gaining a column over time (e.g. V12's
            # person.keycloak_subject) is normal schema evolution, not a
            # reason an append onto that table's existing history should
            # start failing -- hit live (2026-08-23) as deltalake's own
            # SchemaMismatchError the first Airflow run after that column
            # landed, since plain "append" is schema-strict by default.
            write_deltalake(
                str(bronze_root / table), frame.to_arrow(), mode="append", schema_mode="merge"
            )
            counts[table] = frame.height

        return counts
