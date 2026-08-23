"""Copies the DuckDB gold layer into the serving Postgres database that
Metabase and the TMDL semantic model read. Uses DuckDB's ``postgres``
extension to write directly, in-process -- no intermediate CSV or pandas
round-trip.

Gold marts are rebuilt wholesale each run in Phase 1a; incremental
materialization is a Phase 1b concern and would be premature here.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

# The gold marts this materializes, in main_gold -> reporting.<name>. Widen
# this tuple as the gold layer grows further gold models.
GOLD_MARTS = (
    "mart_determination_outcomes",
    "mart_worker_caseload",
    "mart_access_review",
    "mart_payment_accuracy",
    "mart_processing_timeliness",
)


def materialize_gold(duckdb_path: Path | str, serving_dsn: str) -> dict[str, int]:
    """Copies every mart in ``GOLD_MARTS`` from the DuckDB warehouse at
    ``duckdb_path`` into ``reporting.<mart>`` in the serving Postgres
    database. Returns {mart_name: row_count}."""
    # Not opened read_only: DuckDB's postgres extension inherits the parent
    # connection's read-only mode onto every attached database too, and
    # `serving` needs to be written to. This function only ever reads from
    # main_gold.* -- nothing here issues a write against the warehouse file.
    con = duckdb.connect(str(duckdb_path))
    try:
        con.execute("install postgres; load postgres;")
        # serving_dsn always comes from Settings/env, never external input
        con.execute(f"attach '{serving_dsn}' as serving (type postgres)")
        con.execute("create schema if not exists serving.reporting")

        counts: dict[str, int] = {}
        for mart in GOLD_MARTS:
            # mart names always come from GOLD_MARTS, never external input
            con.execute(f"drop table if exists serving.reporting.{mart}")
            con.execute(
                f"create table serving.reporting.{mart} as select * from main_gold.{mart}"
            )
            row = con.execute(f"select count(*) from serving.reporting.{mart}").fetchone()
            assert row is not None
            counts[mart] = row[0]
        return counts
    finally:
        con.close()
