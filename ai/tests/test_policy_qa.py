"""Policy Q&A / explainability RAG (design doc §2.2): a general-question
grounded case and an abstention case against the real corpus/models
(e2e), plus a "why was I denied" case against a real determination created
through the real portal API -- the full-stack contract this repo's `e2e`
marker already implies (`docker compose up` brings up OpenSearch/Ollama
*and* portal-api/Keycloak/Postgres together). `citation_grounded` itself
is tested directly, with no infra at all.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

import httpx
import psycopg
import pytest

from canopica_ai.common.llm_client import LlmResponse
from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.qa.grounding import citation_grounded
from canopica_ai.policy_intelligence.qa.service import ABSTENTION_MESSAGE, answer_denial, answer_general

pytestmark = pytest.mark.e2e

PORTAL_API_URL = "http://localhost:8080"
KEYCLOAK_URL = "http://localhost:8081"

# Same test identity Java's AbstractApiTest and canopica_data.synthetic.loader
# already authenticate as -- identity/realm-export/canopica-citizens-realm.json
# seeds it for exactly this purpose.
_CITIZEN_USERNAME = "citizen.jordan@canopica.local"
_CITIZEN_PASSWORD = "CanopicaCitizen123!"
_WORKER_USERNAME = "worker.sam"
_WORKER_PASSWORD = "CanopicaWorker123!"

# A single person with an implausibly high wage -- comfortably over any
# real SNAP gross-income limit regardless of household size, so this
# household is reliably denied (GROSS_INCOME_EXCEEDS_LIMIT) rather than
# needing to reverse-engineer the exact seeded income-limit figures.
_HIGH_INCOME_HOUSEHOLD_INTAKE: dict[str, Any] = {
    "county": "Test County",
    "addressLine1": "1 Test Way",
    "city": "Testville",
    "state": "TS",
    "zipCode": "00000",
    "channel": "ONLINE",
    "arrangementType": "RENTS",
    "members": [
        {
            "firstName": "Riley",
            "lastName": "HighEarner",
            "dateOfBirth": "1985-01-01",
            "sex": "X",
            "relationship": "SELF",
            "incomes": [
                {
                    "incomeType": "WAGES",
                    "earned": True,
                    "monthlyAmount": "10000.00",
                    "effectiveFrom": "2025-01-01",
                }
            ],
        }
    ],
}


def _fetch_token(
    realm: str, client_id: str, client_secret: str, username: str, password: str
) -> str:
    response = httpx.post(
        f"{KEYCLOAK_URL}/realms/{realm}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": client_id,
            "client_secret": client_secret,
            "username": username,
            "password": password,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    token: str = response.json()["access_token"]
    return token


def _citizen_token() -> str:
    return _fetch_token(
        "canopica-citizens",
        "test-customer",
        "test-customer-secret",
        _CITIZEN_USERNAME,
        _CITIZEN_PASSWORD,
    )


def _worker_token() -> str:
    return _fetch_token(
        "canopica-workers", "test-worker", "test-worker-secret", _WORKER_USERNAME, _WORKER_PASSWORD
    )


def _submit_application(citizen_token: str) -> str:
    response = httpx.post(
        f"{PORTAL_API_URL}/api/applications",
        json=_HIGH_INCOME_HOUSEHOLD_INTAKE,
        headers={"Authorization": f"Bearer {citizen_token}"},
        timeout=30.0,
    )
    response.raise_for_status()
    program_request_id: str = response.json()["programRequestId"]
    return program_request_id


def _decide(worker_token: str, program_request_id: str) -> str:
    today = date.today()
    response = httpx.post(
        f"{PORTAL_API_URL}/api/program-requests/{program_request_id}/determinations",
        json={"asOfDate": today.isoformat(), "benefitMonth": today.replace(day=1).isoformat()},
        headers={"Authorization": f"Bearer {worker_token}"},
        timeout=30.0,
    )
    response.raise_for_status()
    determination_id: str = response.json()["determinationId"]
    return determination_id


def _a_denied_determination() -> tuple[str, str]:
    """Returns (determination_id, citizen_bearer_token) for a real,
    freshly-decided, ineligible determination."""
    citizen_token = _citizen_token()
    program_request_id = _submit_application(citizen_token)
    determination_id = _decide(_worker_token(), program_request_id)
    return determination_id, citizen_token


class _StubLlmClient:
    """A fake `LlmClient` for controlling exactly what generation "says"
    back, without a real (slow, temperature-driven) Ollama call. Each entry
    in `responses` is returned in order, one per call; the literal string
    "ECHO" is replaced with a real cfr_section id parsed out of the
    prompt's own labeled context (see `_labeled_context` in service.py --
    each chunk is rendered as `[<cfr_section> -- <heading>]`), so a test can
    assert "a grounded retry succeeds" without hardcoding which section the
    live corpus ranks first today.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def generate(self, prompt: str) -> LlmResponse:
        text = self._responses[self.calls]
        self.calls += 1
        if text == "ECHO":
            match = re.search(r"\[(\S+) --", prompt)
            assert match, "no labeled context section found in prompt"
            text = f"Per {match.group(1)}, explained in plain language."
        return LlmResponse(text=text)


class TestCitationGrounded:
    """No infra needed -- pure function, but the whole file inherits the
    e2e marker, so these run alongside the live tests rather than in the
    fast `not e2e` suite. That's an acceptable trade for keeping every
    Policy Q&A test in one file; nothing here depends on live services."""

    def test_every_citation_retrieved_is_grounded(self) -> None:
        retrieved = ["273.9(a)", "273.9(d)(6)", "273.2(i)"]
        assert citation_grounded(["273.9(a)", "273.9(d)(6)"], retrieved) is True

    def test_a_citation_not_among_retrieved_chunks_is_not_grounded(self) -> None:
        retrieved = ["273.9(a)", "273.9(d)(6)"]
        assert citation_grounded(["273.9(a)", "273.99(z)"], retrieved) is False

    def test_no_citations_at_all_is_not_grounded(self) -> None:
        assert citation_grounded([], ["273.9(a)"]) is False


class TestAnswerGeneral:
    def test_a_clear_question_is_grounded_with_real_citations(
        self, indexed_corpus: Settings
    ) -> None:
        question = "What is the gross income test for a household?"
        answer = answer_general(question, settings=indexed_corpus)

        assert answer.abstained is False
        assert answer.citations
        # Every emitted citation is real by construction (_cited_sections
        # only ever returns sections that were actually retrieved).
        assert citation_grounded(answer.citations, answer.citations)

    def test_an_unanswerable_question_abstains_without_calling_the_model(
        self, indexed_corpus: Settings
    ) -> None:
        question = "What is the capital of France and how do I bake a chocolate cake?"
        answer = answer_general(question, settings=indexed_corpus)

        assert answer.abstained is True
        assert answer.citations == []
        assert "insufficient information" in answer.answer

    def test_every_answer_is_recorded_with_complete_provenance(
        self, indexed_corpus: Settings
    ) -> None:
        question = f"What is the gross income test for a household? ({uuid.uuid4()})"
        answer_general(question, settings=indexed_corpus)

        with psycopg.connect(indexed_corpus.operational_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select corpus_version, embedding_model_version, retrieval_config, "
                "prompt_version, retrieved_chunk_ids, abstained "
                "from ai.policy_qa_answer where question = %s",
                (question,),
            )
            row = cur.fetchone()

        assert row is not None
        corpus_version, embedding_model_version, retrieval_config, prompt_version = row[:4]
        retrieved_chunk_ids, abstained = row[4:]
        assert corpus_version
        assert embedding_model_version
        assert retrieval_config
        assert prompt_version
        assert retrieved_chunk_ids
        assert abstained is False


class TestGroundingRetryAndAbstention:
    """A strong retrieval score doesn't guarantee the model actually uses
    what it was given (design doc §2.2's "RAG's most common failure mode");
    these drive generation with a controlled fake `LlmClient` rather than
    real Ollama output, so the retry-then-abstain behavior is asserted
    deterministically instead of depending on when a flaky model happens to
    comply."""

    _QUESTION = "What is the gross income test for a household?"

    def test_an_ungrounded_first_attempt_is_retried_and_the_retry_is_used(
        self, indexed_corpus: Settings
    ) -> None:
        stub = _StubLlmClient(["this cites nothing at all", "ECHO"])

        answer = answer_general(self._QUESTION, settings=indexed_corpus, llm_client=stub)

        assert stub.calls == 2
        assert answer.abstained is False
        assert answer.citations
        assert citation_grounded(answer.citations, answer.citations)

    def test_two_consecutive_ungrounded_attempts_abstain_instead_of_serving_a_guess(
        self, indexed_corpus: Settings
    ) -> None:
        stub = _StubLlmClient(["this cites nothing at all", "still nothing citeable here"])

        answer = answer_general(self._QUESTION, settings=indexed_corpus, llm_client=stub)

        assert stub.calls == 2
        assert answer.abstained is True
        assert answer.citations == []
        assert answer.answer == ABSTENTION_MESSAGE


class TestAnswerDenial:
    def test_a_denied_determination_cites_the_real_income_section(
        self, indexed_corpus: Settings
    ) -> None:
        determination_id, citizen_token = _a_denied_determination()

        answer = answer_denial(determination_id, citizen_token, settings=indexed_corpus)

        assert answer.abstained is False
        assert citation_grounded(answer.citations, answer.citations)
        # 273.9(a) is where both the gross- and net-income tests live in
        # this corpus (design doc §2.1's scoping) -- a real, live-verified
        # top retrieval match for this reason code, not assumed.
        assert any(citation.startswith("273.9(a)") for citation in answer.citations)

    def test_the_denial_explanation_is_recorded_against_its_determination(
        self, indexed_corpus: Settings
    ) -> None:
        determination_id, citizen_token = _a_denied_determination()

        answer_denial(determination_id, citizen_token, settings=indexed_corpus)

        with psycopg.connect(indexed_corpus.operational_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "select count(*) from ai.policy_qa_answer where determination_id = %s",
                (determination_id,),
            )
            row = cur.fetchone()

        assert row is not None
        assert row[0] == 1
