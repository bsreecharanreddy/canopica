"""AI-drafted correspondence (design doc §2.4). Most of this file is a
synthetic determination fixture plus a stub LLM, the same split document_
intake's own test file uses for its non-e2e classes -- but unlike that
file's private `_matched_verification_ids`, `service.py`'s own `_fetch_
determination` SQL query (the join across eligibility_determination/
determination_trace/program_request/application/household/person, plus
psycopg's own jsonb-column handling) is never exercised by any synthetic
fixture, since a synthetic `DeterminationRecord` is constructed directly
and never round-trips through that query. `TestDraftAgainstARealStack`
below is what actually proves that query is correct, with a stub LLM
client so it needs no live Ollama, only the real local Postgres.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
import pytest
from pydantic import BaseModel

from canopica_ai.common.llm_client import LlmResponse
from canopica_ai.config import Settings
from canopica_ai.correspondence.draft import ExplanationDraftError, draft_explanation
from canopica_ai.correspondence.schema import DeterminationRecord
from canopica_ai.correspondence.service import (
    UnsupportedLanguageError,
    _select_notice_type,
    draft,
    fill_template,
)
from canopica_ai.correspondence.validate import validate


def _determination(
    *,
    eligible: bool = True,
    has_outstanding_verification: bool = False,
    benefit_amount: str = "170.00",
) -> DeterminationRecord:
    return DeterminationRecord(
        determination_id=UUID("11111111-1111-1111-1111-111111111111"),
        program_request_id=UUID("22222222-2222-2222-2222-222222222222"),
        eligible=eligible,
        benefit_amount=Decimal(benefit_amount),
        reason_code="ELIGIBLE" if eligible else "NET_INCOME_EXCEEDS_LIMIT",
        benefit_month=date(2026, 9, 1),
        as_of_date=date(2026, 8, 28),
        decided_at=datetime(2026, 8, 28, 12, 0, 0),
        trace_facts={"gross_income": "2100.00", "household_size": 3},
        trace_decisions={"net_income": "1200.00", "benefit_amount": benefit_amount},
        household_head_name="Sam Applicant",
        has_outstanding_verification=has_outstanding_verification,
    )


class TestSelectNoticeType:
    """Task 5's own three-way selection (service.py's own docstring):
    OUTSTANDING verifications override eligibility, since a real figure
    that's still provisional is a materially different message than a
    settled one."""

    def test_an_outstanding_verification_takes_pending_verification_even_when_eligible(
        self,
    ) -> None:
        determination = _determination(eligible=True, has_outstanding_verification=True)
        assert _select_notice_type(determination) == "PENDING_VERIFICATION"

    def test_eligible_with_no_outstanding_verification_is_approval(self) -> None:
        determination = _determination(eligible=True, has_outstanding_verification=False)
        assert _select_notice_type(determination) == "APPROVAL"

    def test_ineligible_with_no_outstanding_verification_is_denial(self) -> None:
        determination = _determination(eligible=False, has_outstanding_verification=False)
        assert _select_notice_type(determination) == "DENIAL"


class TestFillTemplate:
    """Every slot but `explanation` is substituted programmatically
    (design doc §2.4) -- exercised per notice_type against a synthetic
    fixture, no LLM or database involved."""

    @pytest.mark.parametrize("notice_type", ["APPROVAL", "DENIAL", "PENDING_VERIFICATION"])
    def test_every_template_fills_with_no_leftover_placeholder(self, notice_type: str) -> None:
        determination = _determination(eligible=(notice_type != "DENIAL"))
        content = fill_template(notice_type, determination, "This is the explanation.")  # type: ignore[arg-type]

        assert "Sam Applicant" in content
        assert "2026-09-01" in content
        assert "This is the explanation." in content
        assert "{" not in content and "}" not in content

    def test_approval_and_pending_verification_show_the_benefit_amount_denial_does_not(
        self,
    ) -> None:
        approval = fill_template("APPROVAL", _determination(eligible=True), "explanation")
        pending_determination = _determination(eligible=True, has_outstanding_verification=True)
        pending = fill_template("PENDING_VERIFICATION", pending_determination, "explanation")
        denial = fill_template("DENIAL", _determination(eligible=False), "explanation")

        assert "$170.00" in approval
        assert "$170.00" in pending
        assert "$170.00" not in denial


class TestValidate:
    """The deterministic pre-check (design doc §2.4) -- exact comparison
    against the determination's own record, never LLM-judged."""

    def test_content_using_only_known_good_figures_passes(self) -> None:
        determination = _determination()
        content = fill_template("APPROVAL", determination, "Your net income was $1,200.00.")

        result = validate(content, determination)

        assert result.passed
        assert result.errors == []

    def test_a_dollar_amount_not_in_the_determination_record_is_caught(self) -> None:
        determination = _determination()
        # $999.00 appears nowhere in trace_facts/trace_decisions/benefit_amount -- exactly the
        # "deliberately-wrong LLM output" scenario Step 7 calls for.
        content = fill_template(
            "APPROVAL", determination, "Your benefit reflects a $999.00 deduction."
        )

        result = validate(content, determination)

        assert not result.passed
        assert any("$999.00" in error for error in result.errors)

    def test_a_date_not_in_the_determination_record_is_caught(self) -> None:
        determination = _determination()
        content = fill_template("APPROVAL", determination, "This applies as of 2099-01-01.")

        result = validate(content, determination)

        assert not result.passed
        assert any("2099-01-01" in error for error in result.errors)

    def test_an_unfilled_template_slot_is_caught(self) -> None:
        determination = _determination()

        result = validate("Dear {household_head_name}, ...", determination)

        assert not result.passed
        assert any("unfilled" in error for error in result.errors)


class TestTranslation:
    """Task 7 (design doc §2.5): a translated draft is checked by the
    *exact same* `validate()` gate as an English one -- these exercise
    that gate against Spanish-language content, no LLM involved (the
    templates and `validate()`'s own regexes are both language-agnostic
    by design: only `explanation` is ever natural-language prose)."""

    def test_a_spanish_notice_using_only_known_good_figures_passes(self) -> None:
        determination = _determination()
        content = fill_template(
            "APPROVAL",
            determination,
            "Su ingreso neto fue de $1,200.00, dentro del límite.",
            language="es",
        )

        result = validate(content, determination)

        assert result.passed
        assert result.errors == []
        assert "Estimado/a Sam Applicant" in content

    def test_a_mistranslated_dollar_amount_is_caught_the_same_way_an_english_one_would_be(
        self,
    ) -> None:
        determination = _determination()
        # $999.00 appears nowhere in trace_facts/trace_decisions/benefit_amount --
        # the same "deliberately wrong LLM output" scenario TestValidate's own
        # English test exercises above, here inside a Spanish-language explanation.
        content = fill_template(
            "APPROVAL",
            determination,
            "Su beneficio refleja una deducción de $999.00.",
            language="es",
        )

        result = validate(content, determination)

        assert not result.passed
        assert any("$999.00" in error for error in result.errors)

    def test_draft_explanation_is_parameterized_by_language_not_a_separate_code_path(self) -> None:
        explanation = draft_explanation(
            "APPROVAL",
            _determination(),
            language="es",
            llm_client=_StubExplanationClient(
                [_explanation_json("Su ingreso estaba dentro del límite.")]
            ),
        )
        assert explanation == "Su ingreso estaba dentro del límite."

    def test_an_unsupported_language_is_rejected_before_touching_the_database(self) -> None:
        with pytest.raises(UnsupportedLanguageError):
            draft(UUID("11111111-1111-1111-1111-111111111111"), language="fr")


class _StubExplanationClient:
    """Same shape document_intake's own _StubStructuredClient takes:
    canned raw JSON strings returned in order, one per call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> LlmResponse:
        if not self._responses:
            raise AssertionError("stub called more times than the test staged responses for")
        return LlmResponse(text=self._responses.pop(0))


def _explanation_json(explanation: str = "Your income was within the limit.") -> str:
    return json.dumps({"explanation": explanation})


class TestDraftExplanationGuardRails:
    """What `draft_explanation()` does with what the model hands back --
    same retry/failure shape document_intake's own TestClassifyGuardRails
    already establishes for classify()."""

    def test_a_valid_response_becomes_the_explanation(self) -> None:
        explanation = draft_explanation(
            "APPROVAL", _determination(), llm_client=_StubExplanationClient([_explanation_json()])
        )
        assert explanation == "Your income was within the limit."

    def test_a_malformed_response_is_retried_once(self) -> None:
        explanation = draft_explanation(
            "APPROVAL",
            _determination(),
            llm_client=_StubExplanationClient(["not valid json", _explanation_json()]),
        )
        assert explanation == "Your income was within the limit."

    def test_two_consecutive_malformed_responses_raise(self) -> None:
        with pytest.raises(ExplanationDraftError):
            draft_explanation(
                "APPROVAL",
                _determination(),
                llm_client=_StubExplanationClient(["not valid json", "still not valid json"]),
            )


def _seed_determination(settings: Settings, *, eligible: bool = True) -> UUID:
    """The minimal person -> household -> application -> program_request
    -> policy_parameter_set -> eligibility_determination -> determination_
    trace chain `service.draft`'s own `_fetch_determination` query joins
    across, inserted directly via SQL against the real local Postgres
    (assumed migrated -- this is the e2e tier, same "make up already ran"
    convention document_intake's own test file states)."""
    person_id, household_id, application_id, program_request_id = (uuid.uuid4() for _ in range(4))
    parameter_set_id, determination_id = uuid.uuid4(), uuid.uuid4()
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
        # effective_from unique per program_code -- derived from the fresh parameter_set_id, same
        # collision-avoidance worker/tests/test_correspondence_consumer.py's own fixture uses.
        effective_from = date(2000, 1, 1) + timedelta(days=parameter_set_id.int % 3650)
        cur.execute(
            "insert into policy_parameter_set "
            "(id, program_code, version_label, effective_from, source_citation, retrieved_on) "
            "values (%s, 'SNAP', %s, %s, 'test fixture', %s)",
            (parameter_set_id, f"SNAP-TEST-{parameter_set_id}", effective_from, date.today()),
        )
        benefit_amount = "170.00" if eligible else "0.00"
        reason_code = "ELIGIBLE" if eligible else "NET_INCOME_EXCEEDS_LIMIT"
        cur.execute(
            "insert into eligibility_determination "
            "(id, program_request_id, benefit_month, as_of_date, eligible, benefit_amount, "
            "reason_code, policy_parameter_set_id, policy_parameter_version, decided_by) "
            "values (%s, %s, '2026-09-01', '2026-08-28', %s, %s, %s, %s, 'SNAP-TEST', 'SYSTEM')",
            (
                determination_id,
                program_request_id,
                eligible,
                benefit_amount,
                reason_code,
                parameter_set_id,
            ),
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
                json.dumps({"net_income": "1200.00", "benefit_amount": benefit_amount}),
            ),
        )
    return determination_id


@pytest.mark.e2e
class TestDraftAgainstARealStack:
    """The one test that needs the real local Postgres -- whether `service.
    draft`'s own `_fetch_determination` query (the five-table join, and
    psycopg's own jsonb-column handling) actually reads back a real
    determination correctly. A stub LLM client stands in for Ollama, since
    what's under test here is the SQL, not generation quality."""

    def test_a_real_determination_drafts_a_notice_with_correct_content(
        self, settings: Settings
    ) -> None:
        determination_id = _seed_determination(settings, eligible=True)

        explanation = "Your net income was within the limit."
        notice = draft(
            determination_id,
            settings=settings,
            llm_client=_StubExplanationClient([_explanation_json(explanation)]),
        )

        assert notice.notice_type == "APPROVAL"
        assert "Sam Applicant" in notice.content
        assert "$170.00" in notice.content
        assert explanation in notice.content
        assert notice.validation_result.passed
        assert notice.validation_result.errors == []

    def test_a_real_determination_drafts_a_spanish_notice_that_passes_the_same_precheck(
        self, settings: Settings
    ) -> None:
        # Task 7: the translated path is the same `draft()` function, parameterized
        # by language -- this mirrors the English test above almost exactly, which
        # is the point.
        determination_id = _seed_determination(settings, eligible=True)

        explanation = "Su ingreso neto estuvo dentro del límite."
        notice = draft(
            determination_id,
            language="es",
            settings=settings,
            llm_client=_StubExplanationClient([_explanation_json(explanation)]),
        )

        assert notice.language == "es"
        assert notice.notice_type == "APPROVAL"
        assert "Sam Applicant" in notice.content
        assert "$170.00" in notice.content
        assert explanation in notice.content
        assert notice.validation_result.passed
        assert notice.validation_result.errors == []
