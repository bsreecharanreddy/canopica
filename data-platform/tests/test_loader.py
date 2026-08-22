import json

import httpx
import pytest

from canopica_data.synthetic.generator import generate_households
from canopica_data.synthetic.loader import post_households

FAKE_TOKEN = "fake-access-token"


def _keycloak_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/realms/canopica-citizens/protocol/openid-connect/token"
    return httpx.Response(200, json={"access_token": FAKE_TOKEN})


def test_posts_the_intake_payload_with_a_real_bearer_token() -> None:
    households = generate_households(2, seed=5)
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            201,
            json={"applicationId": str(_fixed_uuid(1)), "programRequestId": str(_fixed_uuid(2))},
        )

    results = post_households(
        households,
        "http://test",
        transport=httpx.MockTransport(handler),
        keycloak_transport=httpx.MockTransport(_keycloak_handler),
    )

    assert len(results) == 2
    assert len(seen_requests) == 2
    for request in seen_requests:
        assert request.url.path == "/api/applications"
        assert request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
        body = json.loads(request.content)
        assert set(body) == {
            "county", "addressLine1", "city", "state", "zipCode",
            "arrangementType", "paysUtilitiesSeparately", "members",
        }
        assert len(body["members"]) >= 1


def test_retries_once_on_a_connection_error_then_succeeds() -> None:
    households = generate_households(1, seed=6)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(
            201,
            json={"applicationId": str(_fixed_uuid(1)), "programRequestId": str(_fixed_uuid(2))},
        )

    results = post_households(
        households,
        "http://test",
        transport=httpx.MockTransport(handler),
        keycloak_transport=httpx.MockTransport(_keycloak_handler),
    )

    assert attempts == 2
    assert len(results) == 1


def test_raises_on_a_4xx_response() -> None:
    households = generate_households(1, seed=8)

    def handler(request: httpx.Request) -> httpx.Response:
        errors = [{"field": "members", "message": "must not be empty"}]
        return httpx.Response(400, json={"errors": errors})

    with pytest.raises(httpx.HTTPStatusError):
        post_households(
            households,
            "http://test",
            transport=httpx.MockTransport(handler),
            keycloak_transport=httpx.MockTransport(_keycloak_handler),
        )


def _fixed_uuid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"
