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
    transport: httpx.BaseTransport | None = None,
) -> list[IntakeIds]:
    """`transport` is a test seam for `httpx.MockTransport` -- production calls never pass it."""
    with httpx.Client(base_url=base_url, transport=transport, timeout=30.0) as client:
        return [_post_one(client, household) for household in households]


def _post_one(client: httpx.Client, household: SyntheticHousehold) -> IntakeIds:
    payload = household.to_intake_payload()
    headers = {"X-IES-Role": "CUSTOMER"}
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
