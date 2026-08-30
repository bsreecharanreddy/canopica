"""CLI entry point for the Case SLA/Compliance Monitor's batch refresh
(Phase 4 Task 6):

    uv run python -m canopica_ai.sla_monitor.cli refresh

`canopica_pipeline_dag.py`'s `refresh_sla_stall_reasons` task calls this
via `ai/`'s own isolated venv (see `infra/airflow/Dockerfile`) as a
`BashOperator`, the same "isolated tool, called by absolute binary path"
shape `dbt_build` already uses -- not a direct Python import into
Airflow's own shared environment, since nothing has proven ai/'s much
wider dependency set conflict-free against Airflow's own pinned one (see
that Dockerfile's own block comment).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from canopica_ai.sla_monitor.service import refresh_stall_reasons


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canopica_ai.sla_monitor.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "refresh", help="Refresh sla_stall_reason for the current at-risk case set."
    )
    args = parser.parse_args(argv)

    if args.command == "refresh":
        written = refresh_stall_reasons()
        print(f"SLA stall-reason refresh: {written} case(s) written", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
