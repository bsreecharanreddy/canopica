"""Dashboard-authoring copilot (Phase 2 Task 6 plan): drafts new DAX
measures and report visuals for the Power BI semantic model authored as
TMDL under `reporting/semantic-model/` (Phase 1a Task 11).

This is an authoring-time capability, not a live service -- a BI developer
runs the CLI locally, reviews the output like any other diff, and hand-
applies the accepted parts into the real TMDL files. Nothing in this module
writes to `reporting/semantic-model/` itself; it only reads from it.

Same guard-rail shape as the rule-authoring copilot
(`policy_intelligence/rule_authoring/service.py`), narrowed to this
capability's own hallucination risk: a measure or visual naming a table,
column, or existing measure that isn't actually in the model would look
exactly like a real one to a reviewer who doesn't have the TMDL memorized,
so every reference is checked against the real model before the proposal
is returned.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from canopica_ai.common.llm_client import OllamaClient, StructuredLlmClient
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings

PROMPT_VERSION = "v1"

# Same reasoning as rule_authoring's _MAX_ATTEMPTS: one retry treats a
# single bad sample as variance; a second consecutive failure is evidence
# about the request itself.
_MAX_ATTEMPTS = 2

_TABLE_NAME_RE = re.compile(r"^table (\S+)")
_COLUMN_NAME_RE = re.compile(r"^\tcolumn (\S+)", re.MULTILINE)
_MEASURE_NAME_RE = re.compile(r"^\tmeasure '([^']+)'", re.MULTILINE)


class DaxMeasure(BaseModel):
    name: str
    dax_expression: str
    table: str


class VisualSpec(BaseModel):
    title: str
    visual_type: str
    table: str
    fields: list[str] = Field(default_factory=list)


class DashboardProposal(BaseModel):
    new_measures: list[DaxMeasure] = Field(default_factory=list)
    new_visuals: list[VisualSpec] = Field(default_factory=list)
    rationale: str


class ProposalGenerationError(RuntimeError):
    """The model could not produce a proposal that survives validation.

    Raised rather than returning a partial result, for the same reason
    rule_authoring's service raises rather than half-applying: a proposal
    with some references silently dropped is worse than none, because the
    reviewer has no way to see what's missing from the screen in front of
    them.
    """


class _TableSummary(BaseModel):
    name: str
    columns: list[str]
    measures: list[str]

    @property
    def known_fields(self) -> set[str]:
        return set(self.columns) | set(self.measures)


def _read_current_model(settings: Settings) -> list[_TableSummary]:
    """Reads the real TMDL table files as this capability's only source of
    truth for what already exists -- a lightweight text scan rather than a
    full TMDL parser, since the only facts needed are table/column/measure
    names, and the file's own grammar is far larger than that."""
    tables_dir = settings.reporting_semantic_model_dir / "tables"
    summaries: list[_TableSummary] = []
    for path in sorted(tables_dir.glob("*.tmdl")):
        text = path.read_text()
        name_match = _TABLE_NAME_RE.match(text)
        if name_match is None:
            continue
        summaries.append(
            _TableSummary(
                name=name_match.group(1),
                columns=_COLUMN_NAME_RE.findall(text),
                measures=_MEASURE_NAME_RE.findall(text),
            )
        )
    return summaries


def _describe_table(table: _TableSummary) -> str:
    measures = ", ".join(table.measures) or "none"
    return (
        f'- table "{table.name}": columns [{", ".join(table.columns)}]; '
        f"existing measures [{measures}]"
    )


def _proposal_prompt(user_prompt: str, tables: list[_TableSummary]) -> str:
    return (
        "You are helping a BI developer extend a Power BI semantic model "
        "(TMDL) for a benefits-eligibility reporting system. Propose new "
        "DAX measures and/or new report visuals that satisfy the request "
        "below.\n"
        "Rules:\n"
        "- Every table field must be copied character for character from "
        "the list below. Never invent a table name.\n"
        "- Every measure's dax_expression must reference only columns or "
        "measures that already exist on that table, copied character for "
        "character, e.g. AVERAGE('table_name'[column_name]).\n"
        "- Every visual's fields must be columns or measures that already "
        "exist on that table, copied character for character. Never "
        "invent a field.\n"
        "- If nothing in the request can be satisfied from the tables "
        "below, return empty new_measures and new_visuals lists and say "
        "why in rationale.\n"
        "- rationale is one or two sentences explaining what the proposal "
        "adds and why.\n\n"
        "Current model:\n"
        + "\n".join(_describe_table(t) for t in tables)
        + f"\n\nRequest:\n{user_prompt}\n"
    )


def _validate_references(
    proposal: DashboardProposal, tables_by_name: dict[str, _TableSummary]
) -> None:
    """Turns a hallucinated table/column/measure name into a rejection
    rather than a proposal that reaches a reviewer looking exactly like a
    real one -- the same shape as rule_authoring's `_reconcile` guard.

    Also refuses the same measure name proposed twice on one table: TMDL
    has no way to declare two measures under one name, so a duplicate here
    would only surface as a collision once a reviewer tried to hand-apply
    it -- one edit-run away from the model, and measured live to actually
    happen (llama3.2:3b repeated one measure verbatim in the same
    response, 2026-08-24).
    """
    seen_measures: set[tuple[str, str]] = set()
    for measure in proposal.new_measures:
        if not measure.dax_expression.strip():
            raise ValueError(f'measure "{measure.name}" has an empty dax_expression')
        table = tables_by_name.get(measure.table)
        if table is None:
            raise ValueError(f'measure "{measure.name}" references unknown table "{measure.table}"')
        key = (measure.table, measure.name)
        if key in seen_measures:
            raise ValueError(
                f'measure "{measure.name}" on "{measure.table}" was proposed more than once'
            )
        seen_measures.add(key)
    for visual in proposal.new_visuals:
        table = tables_by_name.get(visual.table)
        if table is None:
            raise ValueError(f'visual "{visual.title}" references unknown table "{visual.table}"')
        unknown_fields = [field for field in visual.fields if field not in table.known_fields]
        if unknown_fields:
            raise ValueError(
                f'visual "{visual.title}" references unknown field(s) on '
                f'"{visual.table}": {unknown_fields}'
            )


def propose_dashboard(
    prompt: str,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> DashboardProposal:
    """Drafts a `DashboardProposal` for `prompt` against the real, current
    TMDL model. Raises `ProposalGenerationError` if two consecutive
    attempts fail validation.
    """
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)
    tables = _read_current_model(settings)
    tables_by_name = {table.name: table for table in tables}
    full_prompt = _proposal_prompt(prompt, tables)

    with traced_ai_operation("dashboard_assist.propose_dashboard"):
        last_error: Exception | None = None
        for _ in range(_MAX_ATTEMPTS):
            response = llm_client.generate_structured(full_prompt, DashboardProposal)
            try:
                proposal = DashboardProposal.model_validate_json(response.text)
                _validate_references(proposal, tables_by_name)
            except ValueError as error:
                # Pydantic's ValidationError is a ValueError, same as
                # rule_authoring's service: malformed JSON and a hallucinated
                # reference both mean this attempt produced nothing usable.
                last_error = error
                continue
            return proposal

        raise ProposalGenerationError(
            f"could not produce a valid proposal after {_MAX_ATTEMPTS} attempts: {last_error}"
        )
