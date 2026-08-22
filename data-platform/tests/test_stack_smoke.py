"""Hits every always-up Compose service's own health/root endpoint over
the host's published ports -- proves `make up` produced a stack that
actually answers, not just containers that started."""

import httpx
import pytest


@pytest.mark.e2e
@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://localhost:8080/actuator/health", "UP"),
        ("http://localhost:3000/", "Canopica"),
        ("http://localhost:3001/api/health", "ok"),
        # Keycloak's unauthenticated realm-descriptor endpoint -- proves the
        # canopica-workers realm actually imported, not just that the container
        # is listening.
        ("http://localhost:8081/realms/canopica-workers", "canopica-workers"),
        ("http://localhost:8082/health", "healthy"),
    ],
)
def test_every_service_answers(url: str, expected: str) -> None:
    response = httpx.get(url, timeout=10)
    assert response.status_code == 200
    assert expected in response.text
