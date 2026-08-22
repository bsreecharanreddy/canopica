"""Posts generated households through the real intake API -- deliberately not straight into
Postgres, so generated data passes exactly the validation a real applicant's submission does.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

import httpx
from pydantic import BaseModel

from ies_data.synthetic.models import SyntheticHousehold


class IntakeIds(BaseModel):
    application_id: uuid.UUID
    program_request_id: uuid.UUID


def post_households(
    households: Iterable[SyntheticHousehold],
    base_url: str,
    *,
    keycloak_url: str = "http://localhost:8081",
    transport: httpx.BaseTransport | None = None,
    keycloak_transport: httpx.BaseTransport | None = None,
) -> list[IntakeIds]:
    """`transport`/`keycloak_transport` are test seams for `httpx.MockTransport` -- production
    calls never pass them. Every household is submitted under the same seeded
    `citizen.jordan@ies.local` test identity (`identity/realm-export/ies-citizens-realm.json`)
    -- the *data* is what's synthetic and distinct per household (person, income, expenses...),
    not which citizen account authenticates the submission, and nothing in the schema links a
    program_request back to the submitting identity anyway."""
    token = _fetch_citizen_token(keycloak_url, transport=keycloak_transport)
    with httpx.Client(base_url=base_url, transport=transport, timeout=30.0) as client:
        return [_post_one(client, household, token) for household in households]


def _fetch_citizen_token(keycloak_url: str, *, transport: httpx.BaseTransport | None) -> str:
    with httpx.Client(transport=transport, timeout=30.0) as client:
        response = client.post(
            f"{keycloak_url}/realms/ies-citizens/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "test-customer",
                "client_secret": "test-customer-secret",
                "username": "citizen.jordan@ies.local",
                "password": "IesCitizen123!",
            },
        )
    response.raise_for_status()
    token: str = response.json()["access_token"]
    return token


def _post_one(client: httpx.Client, household: SyntheticHousehold, token: str) -> IntakeIds:
    payload = household.to_intake_payload()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = client.post("/api/applications", json=payload, headers=headers)
    except httpx.ConnectError:
        # One retry -- a cold-starting Compose service is a transient condition, not a data problem.
        response = client.post("/api/applications", json=payload, headers=headers)

    response.raise_for_status()
    body = response.json()
    return IntakeIds(
        application_id=body["applicationId"], program_request_id=body["programRequestId"]
    )
