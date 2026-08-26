"""Unit tests for the Analytics Copilot's own JWT validation (design doc
§2.4 / Task 5 plan: "validated the same way the API validates one, via
the workers realm's JWKS endpoint -- this service is its own resource
server, not routed through the API").

No network and no real Keycloak: a locally generated RSA keypair signs a
token exactly as Keycloak would, and a fake JWKS client (satisfying the one
method `decode_worker_token` actually calls) hands back the public half --
the same "stub the seam, not the library" approach `test_llm_client.py`
already uses for `httpx.post`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from canopica_ai.analytics_copilot.jwt_auth import TokenValidationError, decode_worker_token
from canopica_ai.config import Settings

_ISSUER = "http://localhost:8081/realms/canopica-workers"


@dataclass
class _SigningKey:
    key: RSAPublicKey


class _FakeJwkClient:
    """Stands in for `jwt.PyJWKClient`: hands back whichever public key this
    test wants the token verified against, without a real JWKS fetch."""

    def __init__(self, public_key: RSAPublicKey) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
        return _SigningKey(key=self._public_key)


def _keypair() -> tuple[rsa.RSAPrivateKey, RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _token(private_key: rsa.RSAPrivateKey, **claim_overrides: object) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": "worker-subject-123",
        "iss": _ISSUER,
        "iat": now,
        "exp": now + 300,
        "realm_access": {"roles": ["WORKER"]},
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


class TestDecodeWorkerToken:
    def test_a_validly_signed_token_decodes_to_its_subject_and_roles(self) -> None:
        private_key, public_key = _keypair()
        token = _token(private_key, realm_access={"roles": ["WORKER", "SUPERVISOR"]})

        claims = decode_worker_token(
            token, settings=Settings(), jwk_client=_FakeJwkClient(public_key)
        )

        assert claims.subject == "worker-subject-123"
        assert claims.roles == frozenset({"WORKER", "SUPERVISOR"})

    def test_a_token_with_no_realm_roles_decodes_to_an_empty_role_set(self) -> None:
        private_key, public_key = _keypair()
        token = _token(private_key, realm_access={"roles": []})

        claims = decode_worker_token(
            token, settings=Settings(), jwk_client=_FakeJwkClient(public_key)
        )

        assert claims.roles == frozenset()

    def test_a_token_signed_by_a_different_key_is_rejected(self) -> None:
        private_key, _ = _keypair()
        _, other_public_key = _keypair()
        token = _token(private_key)

        with pytest.raises(TokenValidationError):
            decode_worker_token(
                token, settings=Settings(), jwk_client=_FakeJwkClient(other_public_key)
            )

    def test_an_expired_token_is_rejected(self) -> None:
        private_key, public_key = _keypair()
        now = int(time.time())
        token = _token(private_key, iat=now - 600, exp=now - 300)

        with pytest.raises(TokenValidationError):
            decode_worker_token(
                token, settings=Settings(), jwk_client=_FakeJwkClient(public_key)
            )

    def test_a_token_from_the_wrong_issuer_is_rejected(self) -> None:
        # A citizens-realm token (or any token not from canopica-workers) must not
        # authenticate here -- the whole reason there are two separate realms.
        private_key, public_key = _keypair()
        token = _token(private_key, iss="http://localhost:8081/realms/canopica-citizens")

        with pytest.raises(TokenValidationError):
            decode_worker_token(
                token, settings=Settings(), jwk_client=_FakeJwkClient(public_key)
            )
