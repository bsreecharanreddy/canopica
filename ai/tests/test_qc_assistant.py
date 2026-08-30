"""QC / Payment Error Rate Assistant (design doc §2.3). Most of this file
is a synthetic trace fixture plus a stub LLM, the same split
`test_correspondence.py`'s own module docstring establishes -- but unlike
that file's `_matched_verification_ids`, `service.py`'s own `_fetch_traces`
SQL query (the three-table join across `determination_trace`/
`eligibility_determination`/`payment_error_review`) is never exercised by
any synthetic fixture. `TestSummarizeAgainstARealStack` below is what
actually proves that query is correct, with a stub LLM client so it needs
no live Ollama, only the real local Postgres.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest
from pydantic import BaseModel

from canopica_ai.common.llm_client import LlmResponse
from canopica_ai.config import Settings
from canopica_ai.qc_assistant.draft import DiscrepancyContext, SummaryDraftError, draft_summary
from canopica_ai.qc_assistant.service import (
    DeterminationNotFoundError,
    SummaryGroundingError,
    summarize,
)
from canopica_ai.qc_assistant.validate import grounding_errors, known_good_amounts


class _StubSummaryClient:
    """Same shape `correspondence`'s own `_StubExplanationClient` takes:
    canned raw JSON strings returned in order, one per call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> LlmResponse:
        if not self._responses:
            raise AssertionError("stub called more times than the test staged responses for")
        return LlmResponse(text=self._responses.pop(0))


def _summary_json(summary: str = "The gross income limit changed.") -> str:
    return json.dumps({"summary": summary})


def _context(**overrides: object) -> DiscrepancyContext:
    defaults: dict[str, object] = {
        "original_amount": Decimal("649.00"),
        "reproduced_amount": Decimal("683.00"),
        "error_amount": Decimal("34.00"),
        "original_trace": {"net_income": "1200.00"},
        "reproduced_trace": {"net_income": "1166.00"},
        "policy_parameter_version": "SNAP-FY2026",
    }
    defaults.update(overrides)
    return DiscrepancyContext.model_validate(defaults)


class TestValidate:
    """The deterministic grounding check (design doc §2.3, constraint
    21) -- exact comparison against the diff and both traces, never
    LLM-judged."""

    def test_a_summary_using_only_known_good_figures_passes(self) -> None:
        known = known_good_amounts(_context())
        errors = grounding_errors(
            "The re-derived amount was $683.00, a $34.00 increase over the original $649.00.", known
        )
        assert errors == []

    def test_a_dollar_amount_not_in_the_diff_or_either_trace_is_caught(self) -> None:
        known = known_good_amounts(_context())
        # $999.00 appears nowhere in original/reproduced/error or either trace -- the deliberately
        # wrong LLM output scenario Step 8 calls for.
        errors = grounding_errors("This reflects a $999.00 adjustment.", known)

        assert len(errors) == 1
        assert "$999.00" in errors[0]

    def test_a_negative_diff_is_grounded_regardless_of_which_side_the_sign_lands_on(self) -> None:
        known = known_good_amounts(
            _context(
                reproduced_amount=Decimal("615.00"), error_amount=Decimal("-34.00"),
                original_trace={}, reproduced_trace={},
            )
        )
        assert grounding_errors("The amount decreased by $-34.00.", known) == []
        assert grounding_errors("The amount decreased by -$34.00.", known) == []

    def test_a_figure_buried_in_either_trace_is_recognized(self) -> None:
        known = known_good_amounts(
            _context(
                reproduced_amount=Decimal("649.00"), error_amount=Decimal("0.00"),
                original_trace={"deductions": {"shelter": "712.00"}},
                reproduced_trace={"deductions": {"shelter": "744.00"}},
            )
        )
        errors = grounding_errors("The shelter deduction cap moved from $712.00 to $744.00.", known)
        assert errors == []


class TestDraftSummaryGuardRails:
    """What `draft_summary()` does with what the model hands back -- same
    retry/failure shape `correspondence.draft`'s own guard-rail tests
    already establish."""

    def test_a_valid_response_becomes_the_summary(self) -> None:
        summary = draft_summary(
            _context(), llm_client=_StubSummaryClient([_summary_json("Real explanation.")])
        )
        assert summary == "Real explanation."

    def test_a_malformed_response_is_retried_once(self) -> None:
        summary = draft_summary(
            _context(),
            llm_client=_StubSummaryClient(["not valid json", _summary_json("Real explanation.")]),
        )
        assert summary == "Real explanation."

    def test_two_consecutive_malformed_responses_raise(self) -> None:
        with pytest.raises(SummaryDraftError):
            draft_summary(
                _context(),
                llm_client=_StubSummaryClient(["not valid json", "still not valid json"]),
            )


def _seed_review(settings: Settings) -> tuple[UUID, Decimal, Decimal]:
    """The minimal person -> household -> application -> program_request
    -> policy_parameter_set -> eligibility_determination ->
    determination_trace -> payment_error_review chain `service.summarize`'s
    own `_fetch_traces` query joins across, inserted directly against the
    real local Postgres -- same e2e-tier convention `test_correspondence.
    py`'s own `_seed_determination` establishes."""
    person_id, household_id, application_id, program_request_id = (uuid.uuid4() for _ in range(4))
    parameter_set_id, determination_id, review_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    original_amount, reproduced_amount = Decimal("649.00"), Decimal("683.00")

    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into person (id, first_name, last_name, date_of_birth, ssn_token, sex) "
            "values (%s, 'Sam', 'Applicant', '1990-01-01', %s, 'F')",
            (person_id, f"ssn-token-{person_id}"),
        )
        cur.execute(
            "insert into household "
            "(id, head_person_id, county, address_line1, city, state, zip_code) "
            "values (%s, %s, 'Test County', '1 Test St', 'Testville', 'TS', '00000')",
            (household_id, person_id),
        )
        cur.execute(
            "insert into application (id, household_id, submitted_at, channel) "
            "values (%s, %s, now(), 'ONLINE')",
            (application_id, household_id),
        )
        cur.execute(
            "insert into program_request (id, application_id, program_code, status, requested_on) "
            "values (%s, %s, 'SNAP', 'DETERMINED', %s)",
            (program_request_id, application_id, date.today()),
        )
        # effective_from unique per program_code -- same collision-avoidance
        # test_correspondence.py's own fixture comment gives.
        effective_from = date(2000, 1, 1) + timedelta(days=parameter_set_id.int % 3650)
        cur.execute(
            "insert into policy_parameter_set "
            "(id, program_code, version_label, effective_from, effective_to, source_citation, "
            "retrieved_on) "
            "values (%s, 'SNAP', %s, %s, %s, 'test fixture', %s)",
            (
                parameter_set_id,
                f"SNAP-TEST-{parameter_set_id}",
                effective_from,
                effective_from + timedelta(days=1),
                date.today(),
            ),
        )
        cur.execute(
            "insert into eligibility_determination "
            "(id, program_request_id, benefit_month, as_of_date, eligible, benefit_amount, "
            "reason_code, policy_parameter_set_id, policy_parameter_version, decided_by) "
            "values (%s, %s, '2026-09-01', '2026-08-28', true, %s, 'ELIGIBLE', %s, 'SNAP-TEST', "
            "'SYSTEM')",
            (determination_id, program_request_id, original_amount, parameter_set_id),
        )
        cur.execute(
            "insert into determination_trace "
            "(id, determination_id, input_snapshot, decision_results, dmn_model_name, "
            "dmn_model_hash, engine_version) "
            "values (%s, %s, %s::jsonb, %s::jsonb, 'snap-eligibility', 'test-hash', 'test')",
            (
                uuid.uuid4(),
                determination_id,
                json.dumps({"gross_income": "2100.00"}),
                json.dumps({"net_income": "1200.00", "benefit_amount": str(original_amount)}),
            ),
        )
        cur.execute(
            "insert into payment_error_review "
            "(id, determination_id, original_amount, reproduced_amount, error_amount, "
            "reproduced_trace) "
            "values (%s, %s, %s, %s, %s, %s::jsonb)",
            (
                review_id,
                determination_id,
                original_amount,
                reproduced_amount,
                reproduced_amount - original_amount,
                json.dumps({"net_income": "1166.00", "benefit_amount": str(reproduced_amount)}),
            ),
        )
    return determination_id, original_amount, reproduced_amount


@pytest.mark.e2e
class TestSummarizeAgainstARealStack:
    """The one class that needs the real local Postgres -- whether
    `service.summarize`'s own `_fetch_traces` query (the three-table join,
    and psycopg's own jsonb-column handling) actually reads back a real
    determination/review pair correctly. A stub LLM client stands in for
    Ollama, since what's under test here is the SQL and the grounding
    gate, not generation quality."""

    def test_a_real_review_summarizes_with_a_grounded_response(self, settings: Settings) -> None:
        determination_id, original_amount, reproduced_amount = _seed_review(settings)

        summary = summarize(
            determination_id,
            original_amount,
            reproduced_amount,
            settings=settings,
            llm_client=_StubSummaryClient(
                [_summary_json("The re-derived amount was $683.00, a $34.00 increase.")]
            ),
        )

        assert summary == "The re-derived amount was $683.00, a $34.00 increase."

    def test_an_ungrounded_response_is_retried_then_raises(self, settings: Settings) -> None:
        determination_id, original_amount, reproduced_amount = _seed_review(settings)
        ungrounded = _summary_json("This reflects a $999.00 adjustment.")

        with pytest.raises(SummaryGroundingError):
            summarize(
                determination_id,
                original_amount,
                reproduced_amount,
                settings=settings,
                llm_client=_StubSummaryClient([ungrounded, ungrounded]),
            )

    def test_a_determination_with_no_sampled_review_raises(self, settings: Settings) -> None:
        with pytest.raises(DeterminationNotFoundError):
            summarize(
                uuid.uuid4(), Decimal("1.00"), Decimal("2.00"),
                settings=settings, llm_client=_StubSummaryClient([]),
            )
