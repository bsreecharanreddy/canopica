"""Dashboard-authoring copilot (Task 6 plan). Same shape as
test_rule_authoring.py: unit tests drive a stub structured-generation
client and assert the guard rails between a model's output and a file that
lands in front of a BI developer as a reviewable diff -- what gets
rejected as a hallucinated table/column/measure reference, what gets
retried, and what the rendered TMDL patch actually looks like. The single
`e2e` test at the bottom needs a real model: it asks whether the copilot
can ground a real request in the real, current semantic model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from canopica_ai.common.llm_client import LlmResponse
from canopica_ai.config import Settings
from canopica_ai.dashboard_assist.cli import render_proposal_patch, write_proposal
from canopica_ai.dashboard_assist.service import (
    DashboardProposal,
    DaxMeasure,
    ProposalGenerationError,
    VisualSpec,
    propose_dashboard,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SEMANTIC_MODEL_DIR = REPO_ROOT / "reporting" / "semantic-model"

# The real, committed model has exactly one table today
# (reporting/semantic-model/tables/mart_determination_outcomes.tmdl) --
# these tests read it for real rather than faking a TMDL fixture, so a
# rename of that table or its columns fails here instead of silently
# leaving these tests validating against a model that no longer exists.
_REAL_SETTINGS = Settings(reporting_semantic_model_dir=REAL_SEMANTIC_MODEL_DIR)
_REAL_TABLE = "mart_determination_outcomes"
_REAL_COLUMN = "determination_count"
_REAL_MEASURE = "Determinations"


class _StubStructuredClient:
    """Same shape as test_rule_authoring.py's stub: canned raw JSON
    strings in order, one per call, recording every prompt it was given."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []
        self.schemas: list[type[BaseModel]] = []

    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> LlmResponse:
        self.prompts.append(prompt)
        self.schemas.append(schema)
        if not self._responses:
            raise AssertionError("stub called more times than the test staged responses for")
        return LlmResponse(text=self._responses.pop(0))


def _proposal_json(**overrides: object) -> str:
    body: dict[str, object] = {
        "new_measures": [],
        "new_visuals": [],
        "rationale": "because the request asked for it",
    }
    body.update(overrides)
    return json.dumps(body)


def _propose(*responses: str, prompt: str = "add a measure") -> DashboardProposal:
    return propose_dashboard(
        prompt, settings=_REAL_SETTINGS, llm_client=_StubStructuredClient(list(responses))
    )


class TestReferenceValidation:
    """A hallucinated table, column, or measure name would look exactly
    like a real one to a reviewer who doesn't have the TMDL memorized, so
    every reference has to be checked against the real, current model."""

    def test_a_measure_on_a_real_table_referencing_a_real_column_is_accepted(self) -> None:
        proposal = _propose(
            _proposal_json(
                new_measures=[
                    {
                        "name": "Average Determinations",
                        "dax_expression": f"AVERAGE('{_REAL_TABLE}'[{_REAL_COLUMN}])",
                        "table": _REAL_TABLE,
                    }
                ]
            )
        )

        [measure] = proposal.new_measures
        assert measure.table == _REAL_TABLE

    def test_a_measure_on_a_hallucinated_table_is_refused(self) -> None:
        bad = _proposal_json(
            new_measures=[
                {"name": "Fake", "dax_expression": "1", "table": "mart_that_does_not_exist"}
            ]
        )

        with pytest.raises(ProposalGenerationError, match="unknown table"):
            _propose(bad, bad)

    def test_a_measure_with_an_empty_dax_expression_is_refused(self) -> None:
        bad = _proposal_json(
            new_measures=[{"name": "Empty", "dax_expression": "  ", "table": _REAL_TABLE}]
        )

        with pytest.raises(ProposalGenerationError, match="empty dax_expression"):
            _propose(bad, bad)

    def test_a_visual_referencing_a_real_column_and_a_real_measure_is_accepted(self) -> None:
        proposal = _propose(
            _proposal_json(
                new_visuals=[
                    {
                        "title": "Outcomes by program",
                        "visual_type": "bar_chart",
                        "table": _REAL_TABLE,
                        "fields": ["program_code", _REAL_MEASURE],
                    }
                ]
            )
        )

        [visual] = proposal.new_visuals
        assert visual.fields == ["program_code", _REAL_MEASURE]

    def test_a_visual_on_a_hallucinated_table_is_refused(self) -> None:
        bad = _proposal_json(
            new_visuals=[
                {
                    "title": "Bogus",
                    "visual_type": "card",
                    "table": "mart_that_does_not_exist",
                    "fields": [],
                }
            ]
        )

        with pytest.raises(ProposalGenerationError, match="unknown table"):
            _propose(bad, bad)

    def test_the_same_measure_name_proposed_twice_on_one_table_is_refused(self) -> None:
        # Measured live (2026-08-24): llama3.2:3b repeated one measure
        # verbatim in the same response. TMDL has no way to declare two
        # measures under one name, so this would only surface as a
        # collision once a reviewer tried to hand-apply it.
        duplicate = {
            "name": "Average Benefit Per Eligible Determination",
            "dax_expression": f"AVERAGE('{_REAL_TABLE}'[total_benefit_amount])",
            "table": _REAL_TABLE,
        }
        bad = _proposal_json(new_measures=[duplicate, dict(duplicate)])

        with pytest.raises(ProposalGenerationError, match="proposed more than once"):
            _propose(bad, bad)

    def test_a_visual_referencing_a_hallucinated_field_is_refused(self) -> None:
        bad = _proposal_json(
            new_visuals=[
                {
                    "title": "Bogus",
                    "visual_type": "card",
                    "table": _REAL_TABLE,
                    "fields": ["not_a_real_column_or_measure"],
                }
            ]
        )

        with pytest.raises(ProposalGenerationError, match="unknown field"):
            _propose(bad, bad)

    def test_malformed_output_is_retried_once_and_the_retry_is_used(self) -> None:
        proposal = _propose("this is not JSON at all", _proposal_json())

        assert proposal.rationale == "because the request asked for it"

    def test_two_consecutive_malformed_outputs_raise_rather_than_write_a_broken_file(
        self,
    ) -> None:
        with pytest.raises(ProposalGenerationError, match="could not produce a valid proposal"):
            _propose("not JSON", "still not JSON")

    def test_a_proposal_that_satisfies_nothing_is_still_a_valid_empty_proposal(self) -> None:
        # A request this model has nothing real to ground it in is a real,
        # correct answer -- not an error, and not something to pad with
        # invented tables or fields.
        proposal = _propose(_proposal_json())

        assert proposal.new_measures == []
        assert proposal.new_visuals == []

    def test_the_model_is_constrained_to_the_dashboard_proposal_schema(self) -> None:
        client = _StubStructuredClient([_proposal_json()])

        propose_dashboard("add a measure", settings=_REAL_SETTINGS, llm_client=client)

        schema = client.schemas[0].model_json_schema()
        assert "new_measures" in schema["properties"]
        assert "new_visuals" in schema["properties"]

    def test_the_prompt_grounds_the_model_in_the_real_tables_columns_and_measures(self) -> None:
        client = _StubStructuredClient([_proposal_json()])

        propose_dashboard("add a measure", settings=_REAL_SETTINGS, llm_client=client)

        assert _REAL_TABLE in client.prompts[0]
        assert _REAL_COLUMN in client.prompts[0]
        assert _REAL_MEASURE in client.prompts[0]


class TestRenderProposalPatch:
    """What actually lands on disk for a reviewer to read."""

    def test_measures_are_grouped_by_table_and_written_as_real_tmdl_measures(self) -> None:
        proposal = DashboardProposal(
            new_measures=[
                DaxMeasure(
                    name="Average Determinations",
                    dax_expression=f"AVERAGE('{_REAL_TABLE}'[{_REAL_COLUMN}])",
                    table=_REAL_TABLE,
                )
            ],
            rationale="requested an average",
        )

        text = render_proposal_patch("add an average", proposal, model="llama3.2:3b")

        assert f"table {_REAL_TABLE}" in text
        assert (
            f"measure 'Average Determinations' = AVERAGE('{_REAL_TABLE}'[{_REAL_COLUMN}])" in text
        )

    def test_visuals_are_documented_as_comments_since_tmdl_has_no_visual_syntax(self) -> None:
        proposal = DashboardProposal(
            new_visuals=[
                VisualSpec(
                    title="Outcomes by program",
                    visual_type="bar_chart",
                    table=_REAL_TABLE,
                    fields=["program_code", _REAL_MEASURE],
                )
            ],
            rationale="requested a breakdown by program",
        )

        text = render_proposal_patch("show outcomes by program", proposal, model="llama3.2:3b")

        assert f'// - "Outcomes by program" (bar_chart) on {_REAL_TABLE}' in text

    def test_the_prompt_and_rationale_are_recorded_for_the_reviewer(self) -> None:
        proposal = DashboardProposal(rationale="a good reason for the change")

        text = render_proposal_patch("my original request", proposal, model="llama3.2:3b")

        assert "a good reason for the change" in text
        assert "my original request" in text


class TestWriteProposal:
    def test_writes_a_timestamped_tmdl_file_under_proposals_and_never_touches_the_live_model(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "tables").mkdir()
        (tmp_path / "tables" / "existing.tmdl").write_text("table existing\n")
        settings = Settings(reporting_semantic_model_dir=tmp_path)
        proposal = DashboardProposal(rationale="r")

        output_path = write_proposal("a prompt", proposal, settings=settings)

        assert output_path.parent == tmp_path / "proposals"
        assert output_path.suffix == ".tmdl"
        assert output_path.read_text().startswith("// Canopica dashboard-authoring proposal")
        # The one file under tables/ before this call is still the only one.
        assert [p.name for p in (tmp_path / "tables").iterdir()] == ["existing.tmdl"]


@pytest.mark.e2e
class TestProposeAgainstARealModel:
    """The only test here that needs Ollama: whether the copilot can
    ground a real request in the real, current semantic model, which today
    has exactly one table."""

    def test_a_request_grounded_in_the_real_model_proposes_real_references(self) -> None:
        proposal = propose_dashboard(
            "Add a measure for the total benefit amount per eligible "
            "determination, and a bar chart of determinations by program.",
            settings=_REAL_SETTINGS,
        )

        assert proposal.new_measures or proposal.new_visuals
        for measure in proposal.new_measures:
            assert measure.table == _REAL_TABLE
        for visual in proposal.new_visuals:
            assert visual.table == _REAL_TABLE
