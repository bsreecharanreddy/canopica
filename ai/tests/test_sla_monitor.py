"""Case SLA/Compliance Monitor (design doc §2.4). `TestFindAtRiskCases` and
`TestGatherStallContext` below hit the real local Postgres -- like every
other `@pytest.mark.e2e` class in this repo, that Postgres is the shared
local dev instance other e2e tests also write against, not a fresh
Testcontainers instance per test, so assertions are scoped to the specific
ids each test itself created rather than an exact row count -- the same
"an unscoped count here would be a real, order-dependent flake, not a
hypothetical one" reasoning `QcControllerTest`'s own review-queue test
documents on the Java side.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from uuid import UUID

import httpx
import psycopg
import pytest
from pydantic import BaseModel

from canopica_ai.common.llm_client import LlmResponse
from canopica_ai.config import Settings
from canopica_ai.sla_monitor.prioritize import AtRiskCase, find_at_risk_cases
from canopica_ai.sla_monitor.service import refresh_stall_reasons
from canopica_ai.sla_monitor.summarize import (
    StallContext,
    StallReasonDraftError,
    StallReasonGroundingError,
    draft_grounded_stall_reason,
    draft_stall_reason,
    gather_stall_context,
    grounding_errors,
)


class _StubReasonClient:
    """`responses` items are normally canned JSON strings; an `Exception` instance is raised
    instead, standing in for a real transient failure talking to Ollama itself."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses: list[str | Exception] = list(responses)

    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> LlmResponse:
        if not self._responses:
            raise AssertionError("stub called more times than the test staged responses for")
        next_response = self._responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response
        return LlmResponse(text=next_response)


def _reason_json(reason: str) -> str:
    return json.dumps({"reason": reason})


def _context(**overrides: object) -> StallContext:
    defaults: dict[str, object] = {
        "program_request_id": uuid.uuid4(),
        "days_remaining": 2,
        "outstanding_verification_types": ("INCOME",),
        "last_audit_event_type": "CASE_VIEWED",
        "days_since_last_audit_event": 6,
    }
    defaults.update(overrides)
    return StallContext(**defaults)  # type: ignore[arg-type]


class TestGroundingErrors:
    """The deterministic grounding check (design doc §2.4) -- only real
    outstanding verification types and real day counts may be named."""

    def test_a_reason_using_only_real_fields_passes(self) -> None:
        errors = grounding_errors(
            "Awaiting INCOME verification, due in 2 days, last worker action 6 days ago.",
            _context(),
        )
        assert errors == []

    def test_an_invented_day_count_is_caught(self) -> None:
        errors = grounding_errors("This case is 99 days overdue.", _context())
        assert len(errors) == 1
        assert "99" in errors[0]

    def test_an_invented_verification_type_is_caught(self) -> None:
        # DISABILITY is a real verification.data_element value, but not one this fixture case
        # actually has outstanding (only INCOME is) -- the exact "confident wrong answer" shape
        # this check exists to catch.
        errors = grounding_errors("Awaiting DISABILITY verification.", _context())
        assert len(errors) == 1
        assert "DISABILITY" in errors[0]

    def test_a_reason_with_no_recorded_prior_activity_still_grounds_on_days_remaining_alone(
        self,
    ) -> None:
        context = _context(last_audit_event_type=None, days_since_last_audit_event=None)
        errors = grounding_errors("Awaiting INCOME verification, due in 2 days.", context)
        assert errors == []


class TestDraftStallReasonGuardRails:
    def test_a_valid_response_becomes_the_reason(self) -> None:
        reason = draft_stall_reason(
            _context(), llm_client=_StubReasonClient([_reason_json("Real reason.")])
        )
        assert reason == "Real reason."

    def test_a_malformed_response_is_retried_once(self) -> None:
        reason = draft_stall_reason(
            _context(),
            llm_client=_StubReasonClient(["not valid json", _reason_json("Real reason.")]),
        )
        assert reason == "Real reason."

    def test_two_consecutive_malformed_responses_raise(self) -> None:
        with pytest.raises(StallReasonDraftError):
            draft_stall_reason(
                _context(), llm_client=_StubReasonClient(["not valid json", "still not valid json"])
            )


class TestDraftGroundedStallReason:
    def test_an_ungrounded_response_is_retried_then_raises(self) -> None:
        ungrounded = _reason_json("This case is 99 days overdue.")
        with pytest.raises(StallReasonGroundingError):
            draft_grounded_stall_reason(
                _context(), llm_client=_StubReasonClient([ungrounded, ungrounded])
            )

    def test_a_grounded_retry_after_an_ungrounded_first_attempt_succeeds(self) -> None:
        reason = draft_grounded_stall_reason(
            _context(),
            llm_client=_StubReasonClient(
                [
                    _reason_json("This case is 99 days overdue."),
                    _reason_json("Awaiting INCOME verification."),
                ]
            ),
        )
        assert reason == "Awaiting INCOME verification."


def _seed_at_risk_case(
    settings: Settings, *, requested_on: date, is_expedited: bool = False, status: str = "SUBMITTED"
) -> UUID:
    person_id, household_id, application_id, program_request_id = (uuid.uuid4() for _ in range(4))
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
            "insert into program_request "
            "(id, application_id, program_code, status, requested_on, is_expedited) "
            "values (%s, %s, 'SNAP', %s, %s, %s)",
            (program_request_id, application_id, status, requested_on, is_expedited),
        )
    return program_request_id


@pytest.mark.e2e
class TestFindAtRiskCases:
    def test_ages_a_case_against_the_30_day_standard(self, settings: Settings) -> None:
        program_request_id = _seed_at_risk_case(
            settings, requested_on=date.today() - timedelta(days=10)
        )

        cases = find_at_risk_cases(settings=settings)

        case = next(c for c in cases if c.program_request_id == program_request_id)
        assert case.days_remaining == 20

    def test_ages_an_expedited_case_against_the_7_day_standard(self, settings: Settings) -> None:
        program_request_id = _seed_at_risk_case(
            settings, requested_on=date.today() - timedelta(days=3), is_expedited=True
        )

        cases = find_at_risk_cases(settings=settings)

        case = next(c for c in cases if c.program_request_id == program_request_id)
        assert case.days_remaining == 4

    def test_excludes_determined_and_withdrawn_requests(self, settings: Settings) -> None:
        determined_id = _seed_at_risk_case(settings, requested_on=date.today(), status="DETERMINED")
        withdrawn_id = _seed_at_risk_case(settings, requested_on=date.today(), status="WITHDRAWN")

        ids = {c.program_request_id for c in find_at_risk_cases(settings=settings)}

        assert determined_id not in ids
        assert withdrawn_id not in ids

    def test_orders_most_urgent_first(self, settings: Settings) -> None:
        urgent_id = _seed_at_risk_case(settings, requested_on=date.today() - timedelta(days=25))
        less_urgent_id = _seed_at_risk_case(settings, requested_on=date.today() - timedelta(days=5))

        ids = [c.program_request_id for c in find_at_risk_cases(settings=settings)]

        assert ids.index(urgent_id) < ids.index(less_urgent_id)


@pytest.mark.e2e
class TestGatherStallContext:
    """Proves `gather_stall_context`'s own two-query join (outstanding
    `verification` rows, most recent `audit_event`) reads real data back
    correctly -- the query that matters most, since `test_sla_monitor.
    py`'s own `TestGroundingErrors` above never exercises it."""

    def test_reads_real_outstanding_verification_types_and_the_most_recent_audit_event(
        self, settings: Settings
    ) -> None:
        program_request_id = _seed_at_risk_case(
            settings, requested_on=date.today() - timedelta(days=10)
        )
        with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "insert into verification (id, program_request_id, data_element, status, due_on) "
                "values (%s, %s, 'INCOME', 'OUTSTANDING', %s)",
                (uuid.uuid4(), program_request_id, date.today() + timedelta(days=5)),
            )
            # A satisfied verification must not appear in the outstanding set.
            cur.execute(
                "insert into verification "
                "(id, program_request_id, data_element, status, due_on, satisfied_on) "
                "values (%s, %s, 'IDENTITY', 'RECEIVED', %s, %s)",
                (uuid.uuid4(), program_request_id, date.today(), date.today()),
            )
            cur.execute(
                "insert into audit_event (event_type, actor_id, subject_type, subject_id, payload) "
                "values ('APPLICATION_SUBMITTED', 'SYSTEM', 'program_request', %s, '{}'::jsonb)",
                (str(program_request_id),),
            )

        case = AtRiskCase(
            program_request_id=program_request_id, requested_on=date.today() - timedelta(days=10),
            is_expedited=False, days_remaining=20,
        )
        with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
            context = gather_stall_context(case, cur)

        assert context.outstanding_verification_types == ("INCOME",)
        assert context.last_audit_event_type == "APPLICATION_SUBMITTED"
        assert context.days_since_last_audit_event == 0


@pytest.mark.e2e
class TestRefreshStallReasons:
    """`refresh_stall_reasons`'s own orchestration -- find, draft, ground, and write, with a stub
    LLM client standing in for Ollama so this runs against a real Postgres without a live model.
    Every test here passes `cases` explicitly (the case(s) it just created), rather than letting
    `refresh_stall_reasons` call the live `find_at_risk_cases` query -- this shared dev Postgres has
    accumulated real at-risk rows from every other test's own history (a live-measured 71 of them,
    see service.py's own module docstring), and a stub client only has as many canned responses
    queued as each test itself stages, so processing the *live* population here would consume those
    responses against arbitrary unrelated rows instead of this test's own case."""

    def test_writes_a_grounded_reason_for_a_real_at_risk_case(self, settings: Settings) -> None:
        requested_on = date.today() - timedelta(days=10)
        program_request_id = _seed_at_risk_case(settings, requested_on=requested_on)
        case = AtRiskCase(
            program_request_id=program_request_id, requested_on=requested_on,
            is_expedited=False, days_remaining=20,
        )
        reason_text = "Awaiting no verification, still processing."

        written = refresh_stall_reasons(
            settings=settings,
            cases=[case],
            llm_client=_StubReasonClient([_reason_json(reason_text)]),
        )

        assert written == 1
        with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select reason from sla_stall_reason where program_request_id = %s",
                (str(program_request_id),),
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] == reason_text

    def test_a_fresh_reason_already_present_is_skipped_not_redrafted(
        self, settings: Settings
    ) -> None:
        requested_on = date.today() - timedelta(days=10)
        program_request_id = _seed_at_risk_case(settings, requested_on=requested_on)
        case = AtRiskCase(
            program_request_id=program_request_id, requested_on=requested_on,
            is_expedited=False, days_remaining=20,
        )
        with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "insert into sla_stall_reason (program_request_id, reason, generated_at) "
                "values (%s, 'Original reason.', now())",
                (str(program_request_id),),
            )

        written = refresh_stall_reasons(
            settings=settings,
            cases=[case],
            llm_client=_StubReasonClient([]),  # would raise AssertionError if called
        )

        assert written == 0
        with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select reason from sla_stall_reason where program_request_id = %s",
                (str(program_request_id),),
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] == "Original reason."

    def test_a_grounding_failure_on_one_case_does_not_abort_the_whole_run(
        self, settings: Settings
    ) -> None:
        failing_requested_on = date.today() - timedelta(days=5)
        ok_requested_on = date.today() - timedelta(days=10)
        failing_id = _seed_at_risk_case(settings, requested_on=failing_requested_on)
        ok_id = _seed_at_risk_case(settings, requested_on=ok_requested_on)
        failing_case = AtRiskCase(
            program_request_id=failing_id, requested_on=failing_requested_on,
            is_expedited=False, days_remaining=25,
        )
        ok_case = AtRiskCase(
            program_request_id=ok_id, requested_on=ok_requested_on,
            is_expedited=False, days_remaining=20,
        )
        ungrounded = _reason_json("This case is 99 days overdue.")
        ok_reason_text = "Awaiting no verification, still processing."

        written = refresh_stall_reasons(
            settings=settings,
            cases=[failing_case, ok_case],
            llm_client=_StubReasonClient([ungrounded, ungrounded, _reason_json(ok_reason_text)]),
        )

        assert written == 1
        with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select count(*) from sla_stall_reason where program_request_id = %s",
                (str(failing_id),),
            )
            (failing_count,) = cur.fetchone()  # type: ignore[misc]
            cur.execute(
                "select reason from sla_stall_reason where program_request_id = %s", (str(ok_id),)
            )
            ok_row = cur.fetchone()
        assert failing_count == 0
        assert ok_row is not None
        assert ok_row[0] == "Awaiting no verification, still processing."

    def test_a_transient_ollama_failure_on_one_case_does_not_abort_the_whole_run(
        self, settings: Settings
    ) -> None:
        """Live-measured, not hypothetical (see service.py's own module docstring): a real run
        against this project's own dev stack hit a genuine 500 from Ollama after 16 successfully
        processed cases, which crashed the entire batch before this exception class was added to
        the per-case catch clause."""
        flaky_requested_on = date.today() - timedelta(days=5)
        ok_requested_on = date.today() - timedelta(days=10)
        flaky_id = _seed_at_risk_case(settings, requested_on=flaky_requested_on)
        ok_id = _seed_at_risk_case(settings, requested_on=ok_requested_on)
        flaky_case = AtRiskCase(
            program_request_id=flaky_id, requested_on=flaky_requested_on,
            is_expedited=False, days_remaining=25,
        )
        ok_case = AtRiskCase(
            program_request_id=ok_id, requested_on=ok_requested_on,
            is_expedited=False, days_remaining=20,
        )
        ollama_500 = httpx.HTTPStatusError(
            "Server error '500 Internal Server Error'",
            request=httpx.Request("POST", "http://ollama:11434/api/generate"),
            response=httpx.Response(500, request=httpx.Request("POST", "http://ollama:11434/api/generate")),
        )
        ok_reason_text = "Awaiting no verification, still processing."

        written = refresh_stall_reasons(
            settings=settings,
            cases=[flaky_case, ok_case],
            llm_client=_StubReasonClient([ollama_500, _reason_json(ok_reason_text)]),
        )

        assert written == 1
        with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select count(*) from sla_stall_reason where program_request_id = %s",
                (str(flaky_id),),
            )
            (flaky_count,) = cur.fetchone()  # type: ignore[misc]
            cur.execute(
                "select reason from sla_stall_reason where program_request_id = %s", (str(ok_id),)
            )
            ok_row = cur.fetchone()
        assert flaky_count == 0
        assert ok_row is not None
        assert ok_row[0] == ok_reason_text
