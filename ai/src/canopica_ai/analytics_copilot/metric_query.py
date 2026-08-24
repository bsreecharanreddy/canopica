"""Compiles and executes one MetricFlow query against the DuckDB warehouse
dbt built (design doc `2026-08-24-analytics-semantic-layer-execution-and-
authorization.md`, Option A -- approved 2026-08-24).

Two separate DuckDB connections, deliberately:

* **Compilation** goes through data-platform's own already-built, already-
  tested `mf` binary (Task 4), via `mf query --explain --quiet`, which
  prints nothing but the compiled SQL (verified directly against this
  project's installed dbt-metricflow: `_click_echo` suppresses every
  banner line under `--quiet`, and the final `click.echo(sql)` is
  unconditional). `mf`'s own internal connection -- opened by dbt-duckdb's
  adapter, which has no read-only mode at all (`LocalEnvironment.
  initialize_db` always calls `duckdb.connect(path, read_only=False, ...)`,
  checked directly against the installed package) -- never touches a row,
  because `--explain` only compiles.
* **Execution** is this module's own connection, opened with exactly the
  three session-enforcement controls the design doc's approval settled on.
  Verified live (same probe the design doc records): blocks writes, blocks
  `read_csv`/`read_parquet` against arbitrary filesystem paths, and blocks
  changing any of these settings after connecting.

Not MetricFlow's own Python query engine: that would mean embedding
`dbt-metricflow` a second time in this project (data-platform already has
it) purely to reach the same `mf query --explain` code path this module
gets for free over a subprocess, while *still* being unable to make that
engine's own connection read-only (see above) -- so nothing about session
enforcement would be gained by the heavier route.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel

from canopica_ai.config import Settings


class MetricCompilationError(RuntimeError):
    """`mf query --explain` could not compile the request -- an
    unrecognized metric, dimension, or group-by reference is the expected
    real-world cause (Task 4 hit exactly this for a non-entity-qualified
    group-by name; MetricFlow's own error message is preserved here rather
    than re-worded, since it already names the offending reference)."""


class QueryExecution(BaseModel):
    compiled_sql: str
    rows: list[dict[str, Any]]


def compile_metric_query(
    metric_names: Sequence[str],
    group_by_names: Sequence[str],
    *,
    filters: Sequence[str] = (),
    settings: Settings,
) -> str:
    """Returns the exact SQL MetricFlow compiled for this request -- never
    LLM-authored (design doc §2.4's "governed semantic layer, not
    text-to-SQL"). Raises `MetricCompilationError` if compilation fails,
    e.g. a group-by name the manifest does not recognize.
    """
    args: list[str] = [
        str(settings.mf_binary_path.resolve()),
        "query",
        "--metrics",
        ",".join(metric_names),
        "--explain",
        "--quiet",
    ]
    if group_by_names:
        args += ["--group-by", ",".join(group_by_names)]
    for filter_expression in filters:
        args += ["--where", filter_expression]

    # cwd must be the dbt project (mf reads dbt_project.yml/profiles.yml/
    # target/semantic_manifest.json relative to it) -- every path handed to
    # the subprocess is resolved to absolute first, since a relative one
    # would otherwise be interpreted against *this* cwd, not this caller's.
    result = subprocess.run(
        args,
        cwd=settings.data_platform_dbt_project_dir.resolve(),
        env={**os.environ, "CANOPICA_DUCKDB_PATH": str(settings.duckdb_path.resolve())},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MetricCompilationError(result.stdout + result.stderr)
    return result.stdout.strip()


def execute_readonly(sql: str, duckdb_path: Path) -> list[dict[str, Any]]:
    """Runs already-compiled `sql` against `duckdb_path` on a connection
    that cannot write, cannot reach any file the query doesn't already
    name, and cannot have either of those loosened after connecting."""
    connection = duckdb.connect(
        str(duckdb_path.resolve()),
        read_only=True,
        config={"enable_external_access": "false", "lock_configuration": "true"},
    )
    try:
        result = connection.execute(sql)
        columns = [description[0] for description in result.description]
        return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    finally:
        connection.close()


def run_metric_query(
    metric_names: Sequence[str],
    group_by_names: Sequence[str],
    *,
    filters: Sequence[str] = (),
    settings: Settings | None = None,
) -> QueryExecution:
    settings = settings or Settings()
    compiled_sql = compile_metric_query(
        metric_names, group_by_names, filters=filters, settings=settings
    )
    rows = execute_readonly(compiled_sql, settings.duckdb_path)
    return QueryExecution(compiled_sql=compiled_sql, rows=rows)
