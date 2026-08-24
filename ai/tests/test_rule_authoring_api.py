"""The HTTP wire contract between the Java portal and the rule-authoring
copilot.

Worth its own tests rather than folding into `test_rule_authoring.py`,
because this is the one seam where nothing else would catch a mistake: the
service tests speak Python objects, and `PolicyParameterPublishServiceTest`
stubs the client interface rather than crossing the wire. A camelCase/
snake_case mismatch here would compile, type-check and pass both suites,
and only fail once the two services are actually deployed together.

No model and no network: the service function is substituted, so these
assert on serialisation and status codes alone.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from canopica_ai.policy_intelligence.rule_authoring import api
from canopica_ai.policy_intelligence.rule_authoring.schema import ParameterProposal, ProposedParameter
from canopica_ai.policy_intelligence.rule_authoring.service import ProposalGenerationError

_SET_ID = UUID("9f1c0e10-0000-4000-8000-000000000001")

_REQUEST_BODY: dict[str, Any] = {
    "documentExcerpt": "The maximum allotment for a household of one increases to $298.",
    "currentParameterSetId": str(_SET_ID),
    "currentValues": [
        {
            "name": "MAX_ALLOTMENT",
            "householdSize": 1,
            "value": "292",
            "unit": "USD_PER_MONTH",
        }
    ],
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(api.app)


def _proposal() -> ParameterProposal:
    return ParameterProposal(
        parameter_set_id=_SET_ID,
        proposed_values=[
            ProposedParameter(
                name="MAX_ALLOTMENT",
                household_size=1,
                old_value=Decimal("292"),
                new_value=Decimal("298"),
                unit="USD_PER_MONTH",
                rationale="FY2026 COLA",
            )
        ],
        source_excerpt="excerpt",
        generation_model="llama3.2:3b",
        prompt_version="v1",
    )


class TestProposeEndpoint:
    def test_a_camelcase_request_reaches_the_service_unmangled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        def fake_propose(
            excerpt: str, set_id: UUID, current_values: list[Any]
        ) -> ParameterProposal:
            seen["excerpt"] = excerpt
            seen["set_id"] = set_id
            seen["current_values"] = current_values
            return _proposal()

        monkeypatch.setattr(api, "propose_parameter_changes", fake_propose)

        response = client.post("/rule-authoring/propose", json=_REQUEST_BODY)

        assert response.status_code == 200
        assert seen["set_id"] == _SET_ID
        [current] = seen["current_values"]
        assert current.household_size == 1
        assert current.value == Decimal("292")

    def test_the_response_is_camelcase_with_money_as_strings(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(api, "propose_parameter_changes", lambda *_: _proposal())

        body = client.post("/rule-authoring/propose", json=_REQUEST_BODY).json()

        assert body["parameterSetId"] == str(_SET_ID)
        [change] = body["proposedValues"]
        assert change["householdSize"] == 1
        # Money crosses the wire as a string the whole way: Java reads these
        # into BigDecimal, and a JSON number would have gone through a
        # double on one side or the other first.
        assert change["oldValue"] == "292"
        assert change["newValue"] == "298"

    def test_a_generation_failure_is_a_502_not_a_500(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The portal needs to tell "the copilot could not draft this" apart
        # from "the copilot is broken" -- the first is a normal outcome an
        # admin should see explained, the second is an incident.
        def fail(*_: Any) -> ParameterProposal:
            raise ProposalGenerationError("could not produce a valid proposal")

        monkeypatch.setattr(api, "propose_parameter_changes", fail)

        response = client.post("/rule-authoring/propose", json=_REQUEST_BODY)

        assert response.status_code == 502
        assert "could not produce a valid proposal" in response.json()["detail"]

    def test_an_unknown_unit_is_rejected_at_the_edge(self, client: TestClient) -> None:
        body = {
            **_REQUEST_BODY,
            "currentValues": [
                {
                    "name": "MAX_ALLOTMENT",
                    "householdSize": 1,
                    "value": "292",
                    "unit": "EUROS_PER_FORTNIGHT",
                }
            ],
        }

        assert client.post("/rule-authoring/propose", json=body).status_code == 422
