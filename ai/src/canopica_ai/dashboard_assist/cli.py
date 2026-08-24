"""CLI entry point for the dashboard-authoring copilot (Task 6):

    uv run python -m canopica_ai.dashboard_assist.cli propose --prompt "..."

Writes the proposal as a timestamped `.tmdl`-formatted patch file under
`reporting/semantic-model/proposals/` -- reviewable via `git diff` against
the real model. This command never writes into the live TMDL files
themselves; see `reporting/README.md` for the manual review/apply step.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from canopica_ai.config import Settings
from canopica_ai.dashboard_assist.service import DashboardProposal, propose_dashboard


def render_proposal_patch(prompt: str, proposal: DashboardProposal, *, model: str) -> str:
    """Formats `proposal` as TMDL-style text. Measures are real TMDL
    (`table X` / `measure 'Y' = ...`), since Tabular Editor's own format is
    exactly that; visuals are documented as comments because TMDL has no
    report/visual representation at all -- inventing one here would make
    the output look machine-applicable when it isn't."""
    lines = [
        f"// Canopica dashboard-authoring proposal -- generated {datetime.now(UTC).isoformat()}",
        f"// Prompt: {prompt!r}",
        f"// Model: {model}",
        f"// Rationale: {proposal.rationale}",
        "//",
        "// Review like any other diff, then hand-apply the accepted parts into",
        "// the real TMDL files under reporting/semantic-model/ (or script the",
        "// merge via Tabular Editor's CLI) -- nothing here is written into the",
        "// live model. See reporting/README.md.",
        "",
    ]

    by_table: dict[str, list[str]] = {}
    for measure in proposal.new_measures:
        by_table.setdefault(measure.table, []).append(
            f"\tmeasure '{measure.name}' = {measure.dax_expression}"
        )
    for table, measure_lines in by_table.items():
        lines.append(f"table {table}")
        lines.extend(measure_lines)
        lines.append("")

    if proposal.new_visuals:
        lines.append(
            "// Proposed visuals (TMDL has no report/visual representation -- apply"
        )
        lines.append(
            "// these by hand in Power BI Desktop/Service's report view):"
        )
        for visual in proposal.new_visuals:
            fields = ", ".join(visual.fields)
            lines.append(
                f'// - "{visual.title}" ({visual.visual_type}) on {visual.table}: [{fields}]'
            )
        lines.append("")

    return "\n".join(lines)


def write_proposal(prompt: str, proposal: DashboardProposal, *, settings: Settings) -> Path:
    output_dir = settings.reporting_semantic_model_dir / "proposals"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"{timestamp}-proposal.tmdl"
    output_path.write_text(
        render_proposal_patch(prompt, proposal, model=settings.ollama_generation_model)
    )
    return output_path


def _run_propose(args: argparse.Namespace) -> None:
    settings = Settings()
    proposal = propose_dashboard(args.prompt, settings=settings)
    output_path = write_proposal(args.prompt, proposal, settings=settings)
    print(f"wrote {output_path}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m canopica_ai.dashboard_assist.cli")
    subparsers = parser.add_subparsers(required=True)

    propose_parser = subparsers.add_parser(
        "propose", help="Draft a dashboard change proposal from a natural-language request."
    )
    propose_parser.add_argument("--prompt", required=True)
    propose_parser.set_defaults(func=_run_propose)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
