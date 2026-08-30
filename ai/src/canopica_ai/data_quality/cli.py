"""CLI entry point for the data-quality failure -> summary pipeline step
(Phase 4 Task 9):

    uv run python -m canopica_ai.data_quality.cli refresh --run-results <path>

`<path>` is dbt's own `target/run_results.json` from the `dbt build` that
just ran -- this reads only its `metadata.invocation_id`, so
`refresh_data_quality_incidents` scopes to exactly that invocation's own
failures. `canopica_pipeline_dag.py`'s `refresh_data_quality_incidents`
task calls this via `ai/`'s own isolated venv, the same `BashOperator`
shape `refresh_sla_stall_reasons` already uses.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from canopica_ai.data_quality.service import refresh_data_quality_incidents


def _read_invocation_id(run_results_path: Path) -> str:
    payload = json.loads(run_results_path.read_text())
    return str(payload["metadata"]["invocation_id"])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canopica_ai.data_quality.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Summarize this dbt invocation's own failed tests into data_quality_incident.",
    )
    refresh_parser.add_argument(
        "--run-results", required=True, type=Path, help="Path to dbt's target/run_results.json"
    )
    args = parser.parse_args(argv)

    if args.command == "refresh":
        invocation_id = _read_invocation_id(args.run_results)
        written = refresh_data_quality_incidents(invocation_id=invocation_id)
        print(f"Data-quality incident refresh: {written} incident(s) written", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
