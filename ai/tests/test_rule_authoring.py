"""Rule-authoring copilot (design doc §2.3).

Two layers, deliberately separated. The unit tests below drive a stub LLM
and assert the guard rails that stand between a model's output and a
published benefit figure -- what gets rejected, what gets overwritten with
the truth from the database, what gets retried. Those guards are the whole
point of this capability under CLAUDE.md's governing principle (AI drafts,
humans and deterministic systems decide), so they're tested without any
infrastructure at all and run on every push. The single `e2e` test at the
bottom is the one that needs a real model: it asks whether the copilot can
actually read a COLA memo, which no stub can answer.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from canopica_ai.common.llm_client import LlmResponse
from canopica_ai.policy_intelligence.rule_authoring.schema import (
    CurrentParameter,
    ParameterProposal,
    ProposedParameter,
)
from canopica_ai.policy_intelligence.rule_authoring.service import (
    ProposalGenerationError,
    propose_parameter_changes,
)

_SET_ID = UUID("9f1c0e10-0000-4000-8000-000000000001")

# A deliberately tiny slice of the real FY2025 seed (V4 migration) -- enough
# to exercise both a size-scoped figure and a scalar rate.
_CURRENT_VALUES = [
    CurrentParameter(
        name="MAX_ALLOTMENT", household_size=1, value=Decimal("292"), unit="USD_PER_MONTH"
    ),
    CurrentParameter(
        name="STANDARD_DEDUCTION", household_size=1, value=Decimal("204"), unit="USD_PER_MONTH"
    ),
    CurrentParameter(
        name="EARNED_INCOME_DEDUCTION_RATE",
        household_size=None,
        value=Decimal("0.20"),
        unit="RATE",
    ),
]

_EXCERPT = "The maximum allotment for a household of one increases to $298."


class _StubStructuredClient:
    """Returns canned raw JSON strings in order, one per call, so a test can
    stage exactly the malformed-then-valid sequence the retry path exists
    for. Records every prompt it was given."""

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


def _model_json(*values: dict[str, object]) -> str:
    return json.dumps({"proposed_values": list(values)})


def _propose(*responses: str) -> ParameterProposal:
    return propose_parameter_changes(
        _EXCERPT,
        _SET_ID,
        _CURRENT_VALUES,
        llm_client=_StubStructuredClient(list(responses)),
    )


class TestProposedParameterBounds:
    """Design-doc §2.3 narrows this copilot to *values*, never rule logic --
    so the values themselves are where validation has to bite. These bounds
    are about the value's own domain (a rate is a fraction, a dollar figure
    is not negative). How *large* a change is plausible is deliberately not
    checked here: that is the human reviewer's judgement, and a hard cap
    would reject a legitimate large adjustment while teaching nobody
    anything."""

    def _parameter(self, **overrides: object) -> ProposedParameter:
        fields: dict[str, object] = {
            "name": "MAX_ALLOTMENT",
            "household_size": 1,
            "old_value": Decimal("292"),
            "new_value": Decimal("298"),
            "unit": "USD_PER_MONTH",
            "rationale": "FY2026 COLA",
        }
        return ProposedParameter(**{**fields, **overrides})  # type: ignore[arg-type]

    def test_a_plausible_cola_adjustment_is_accepted(self) -> None:
        assert self._parameter().new_value == Decimal("298")

    def test_a_negative_dollar_amount_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._parameter(new_value=Decimal("-1"))

    def test_a_rate_above_one_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._parameter(
                name="EARNED_INCOME_DEDUCTION_RATE",
                household_size=None,
                unit="RATE",
                old_value=Decimal("0.20"),
                new_value=Decimal("1.5"),
            )

    def test_a_household_size_outside_the_schemas_range_is_rejected(self) -> None:
        # Mirrors V3's own `household_size between 1 and 8` CHECK -- caught
        # here rather than as a constraint violation eight layers later.
        with pytest.raises(ValidationError):
            self._parameter(household_size=9)

    def test_an_unknown_unit_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._parameter(unit="EUROS_PER_FORTNIGHT")


class TestProposalGuardRails:
    """What the service does with what the model hands back."""

    def test_a_valid_response_becomes_a_proposal_against_the_supplied_set(self) -> None:
        proposal = _propose(
            _model_json(
                {
                    "name": "MAX_ALLOTMENT",
                    "household_size": 1,
                    "new_value": "298",
                    "rationale": "FY2026 COLA raises the one-person allotment",
                }
            )
        )

        assert proposal.parameter_set_id == _SET_ID
        assert proposal.source_excerpt == _EXCERPT
        [change] = proposal.proposed_values
        assert change.name == "MAX_ALLOTMENT"
        assert change.new_value == Decimal("298")

    def test_the_old_value_and_unit_come_from_the_database_not_the_model(self) -> None:
        # The model is never asked for these and is never believed about
        # them: `old_value` is what the diff is *against*, and a wrong one
        # would make the reviewer's screen lie about what is changing.
        proposal = _propose(
            _model_json(
                {
                    "name": "MAX_ALLOTMENT",
                    "household_size": 1,
                    "new_value": "298",
                    "rationale": "FY2026 COLA",
                }
            )
        )

        [change] = proposal.proposed_values
        assert change.old_value == Decimal("292")
        assert change.unit == "USD_PER_MONTH"

    def test_a_parameter_that_does_not_exist_in_the_current_set_is_refused(self) -> None:
        # This copilot proposes new *values* for existing figures; inventing
        # a parameter name is out of its scope by design (§2.3), and a
        # hallucinated name reaching the reviewer would look exactly like a
        # real policy change to someone who doesn't know the schema.
        with pytest.raises(ProposalGenerationError, match="not in the current parameter set"):
            _propose(
                _model_json(
                    {
                        "name": "TELEWORK_ALLOWANCE",
                        "household_size": 1,
                        "new_value": "50",
                        "rationale": "invented",
                    }
                ),
                _model_json(
                    {
                        "name": "TELEWORK_ALLOWANCE",
                        "household_size": 1,
                        "new_value": "50",
                        "rationale": "invented again",
                    }
                ),
            )

    def test_a_size_scoped_parameter_proposed_for_the_wrong_size_is_refused(self) -> None:
        with pytest.raises(ProposalGenerationError, match="not in the current parameter set"):
            _propose(
                _model_json(
                    {
                        "name": "MAX_ALLOTMENT",
                        "household_size": 6,
                        "new_value": "1400",
                        "rationale": "size not supplied to this call",
                    }
                ),
                _model_json(
                    {
                        "name": "MAX_ALLOTMENT",
                        "household_size": 6,
                        "new_value": "1400",
                        "rationale": "size not supplied to this call",
                    }
                ),
            )

    def test_malformed_output_is_retried_once_and_the_retry_is_used(self) -> None:
        proposal = _propose(
            "this is not JSON at all",
            _model_json(
                {
                    "name": "MAX_ALLOTMENT",
                    "household_size": 1,
                    "new_value": "298",
                    "rationale": "FY2026 COLA",
                }
            ),
        )

        [change] = proposal.proposed_values
        assert change.new_value == Decimal("298")

    def test_two_consecutive_malformed_outputs_raise_rather_than_half_apply(self) -> None:
        # The failure mode this exists to prevent: a partially-parsed
        # proposal, where some figures made it through and others silently
        # did not, is far worse than no proposal -- the reviewer has no way
        # to see what is missing.
        with pytest.raises(ProposalGenerationError, match="could not produce a valid proposal"):
            _propose("not JSON", "still not JSON")

    def test_a_value_the_model_writes_as_prose_is_rejected(self) -> None:
        with pytest.raises(ProposalGenerationError):
            _propose(
                _model_json(
                    {
                        "name": "MAX_ALLOTMENT",
                        "household_size": 1,
                        "new_value": "about three hundred dollars",
                        "rationale": "vague",
                    }
                ),
                _model_json(
                    {
                        "name": "MAX_ALLOTMENT",
                        "household_size": 1,
                        "new_value": "about three hundred dollars",
                        "rationale": "vague",
                    }
                ),
            )

    def test_the_same_parameter_proposed_twice_is_refused(self) -> None:
        # Two rows for one (name, household size) would collide on V3's
        # `policy_parameter_unique` constraint at publish time -- a failure
        # a whole review cycle later, on the one action that is supposed to
        # be safe because a human already checked it.
        with pytest.raises(ProposalGenerationError, match="proposed more than once"):
            _propose(
                _model_json(
                    {
                        "name": "MAX_ALLOTMENT",
                        "household_size": 1,
                        "new_value": "298",
                        "rationale": "first",
                    },
                    {
                        "name": "MAX_ALLOTMENT",
                        "household_size": 1,
                        "new_value": "301",
                        "rationale": "second, contradicting the first",
                    },
                ),
                _model_json(
                    {
                        "name": "MAX_ALLOTMENT",
                        "household_size": 1,
                        "new_value": "298",
                        "rationale": "first",
                    },
                    {
                        "name": "MAX_ALLOTMENT",
                        "household_size": 1,
                        "new_value": "301",
                        "rationale": "second, contradicting the first",
                    },
                ),
            )

    def test_a_value_identical_to_the_current_one_is_not_offered_as_a_change(self) -> None:
        # Restating an unchanged figure is a normal thing for a model to do
        # when the excerpt says "remains 20 percent". It isn't wrong, it
        # just isn't a change -- and a diff screen padded with no-op rows is
        # how a reviewer stops reading the rows carefully.
        proposal = _propose(
            _model_json(
                {
                    "name": "MAX_ALLOTMENT",
                    "household_size": 1,
                    "new_value": "298",
                    "rationale": "FY2026 COLA",
                },
                {
                    "name": "EARNED_INCOME_DEDUCTION_RATE",
                    "household_size": None,
                    "new_value": "0.20",
                    "rationale": "unchanged by this memo",
                },
            )
        )

        assert [change.name for change in proposal.proposed_values] == ["MAX_ALLOTMENT"]

    def test_a_proposal_that_changes_nothing_is_still_a_valid_empty_proposal(self) -> None:
        # An excerpt that turns out to adjust nothing this system tracks is
        # a real, correct answer -- not an error, and not something to
        # pad with invented changes.
        proposal = _propose(_model_json())

        assert proposal.proposed_values == []

    def test_the_model_is_constrained_to_a_schema_not_just_asked_nicely(self) -> None:
        client = _StubStructuredClient(
            [
                _model_json(
                    {
                        "name": "MAX_ALLOTMENT",
                        "household_size": 1,
                        "new_value": "298",
                        "rationale": "FY2026 COLA",
                    }
                )
            ]
        )

        propose_parameter_changes(_EXCERPT, _SET_ID, _CURRENT_VALUES, llm_client=client)

        assert "proposed_values" in client.schemas[0].model_json_schema()["properties"]


# What the API actually sends: the whole effective parameter set, not a
# hand-picked slice of it. Real FY2025 figures (V4 migration), trimmed to
# sizes 1-3 to keep the prompt small -- the shape is what matters, and the
# excerpt below only ever speaks about sizes in that range.
_FULL_CURRENT_VALUES = [
    CurrentParameter(
        name="MAX_ALLOTMENT", household_size=size, value=value, unit="USD_PER_MONTH"
    )
    for size, value in ((1, Decimal("292")), (2, Decimal("536")), (3, Decimal("768")))
] + [
    CurrentParameter(
        name="STANDARD_DEDUCTION", household_size=size, value=Decimal("204"), unit="USD_PER_MONTH"
    )
    for size in (1, 2, 3)
] + [
    CurrentParameter(
        name="EARNED_INCOME_DEDUCTION_RATE",
        household_size=None,
        value=Decimal("0.20"),
        unit="RATE",
    ),
]


@pytest.mark.e2e
class TestProposeAgainstARealModel:
    """The only test here that needs Ollama: whether the copilot can read a
    COLA memo at all. Written in the shape a real FNS adjustment memo takes
    -- one figure stated for a single household size, another stated once
    for a range of sizes, and a third explicitly left alone -- because each
    of those three is a distinct thing the copilot has to get right, and
    the third is the one where being wrong means inventing policy."""

    def test_a_cola_excerpt_produces_the_adjustment_a_human_would_read(self) -> None:
        excerpt = (
            "SNAP Fiscal Year 2026 Cost-of-Living Adjustments. Effective October 1, 2025, "
            "in the 48 contiguous States and the District of Columbia, the maximum monthly "
            "allotment for a household of one increases from $292 to $298. The standard "
            "deduction for household sizes one through three increases from $204 to $210. "
            "The earned income deduction remains 20 percent."
        )

        proposal = propose_parameter_changes(excerpt, _SET_ID, _FULL_CURRENT_VALUES)

        changes = {
            (change.name, change.household_size): change.new_value
            for change in proposal.proposed_values
        }
        assert changes.get(("MAX_ALLOTMENT", 1)) == Decimal("298")
        # Stated once, for a range -- every size in it has to be picked up,
        # since a parameter set that raises the deduction for a one-person
        # household but not a three-person one is not what the memo said.
        assert changes.get(("STANDARD_DEDUCTION", 1)) == Decimal("210")
        assert changes.get(("STANDARD_DEDUCTION", 2)) == Decimal("210")
        assert changes.get(("STANDARD_DEDUCTION", 3)) == Decimal("210")
        # The excerpt raises the allotment only for a household of one, and
        # says the earned-income deduction is unchanged. Proposing anything
        # for these is the model inventing policy, which is the failure this
        # whole capability is shaped to prevent.
        assert ("MAX_ALLOTMENT", 2) not in changes
        assert ("MAX_ALLOTMENT", 3) not in changes
        assert ("EARNED_INCOME_DEDUCTION_RATE", None) not in changes
