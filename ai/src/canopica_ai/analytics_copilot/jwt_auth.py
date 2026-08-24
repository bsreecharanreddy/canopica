"""Worker-realm JWT validation for the Analytics Copilot (design doc §2.4;
Task 5 plan: "validated the same way the portal validates one, via the
workers realm's JWKS endpoint -- this service is its own resource server,
not routed through the portal").

Mirrors `portal/src/main/java/.../SecurityConfig.java`'s own worker chain:
signature verified against the realm's live JWKS, `iss` compared against
the issuer string, expiry checked, `realm_access.roles` read for the same
WORKER/SUPERVISOR/ADMIN roles the Java side grants -- but independently,
because this service never sees a token the portal has already validated.
No audience check, matching `JwtValidators.createDefaultWithIssuer`: these
tokens carry no `aud` claim Keycloak's default client scopes would set.
"""

from __future__ import annotations

from typing import Any, Protocol

import jwt
from jwt import PyJWKClient
from pydantic import BaseModel

from canopica_ai.config import Settings


class TokenValidationError(RuntimeError):
    """A worker-realm bearer token failed signature, issuer, or expiry
    checks. Raised rather than returning `None`, so a caller cannot
    accidentally treat "invalid" as "no claims" and proceed unauthenticated.
    """


class WorkerClaims(BaseModel):
    subject: str
    roles: frozenset[str]

    def has_role(self, role: str) -> bool:
        return role in self.roles


class _SigningKey(Protocol):
    key: Any


class _SigningKeyClient(Protocol):
    """The one `PyJWKClient` method this module calls -- narrowed so a test
    can supply a fake without a real JWKS fetch, the same seam
    `StructuredLlmClient` gives `common/llm_client.py`'s callers."""

    def get_signing_key_from_jwt(self, token: str) -> _SigningKey: ...


def decode_worker_token(
    token: str,
    *,
    settings: Settings | None = None,
    jwk_client: _SigningKeyClient | None = None,
) -> WorkerClaims:
    """Verifies `token` against the workers realm's own signing keys and
    returns its subject and realm roles.

    Raises `TokenValidationError` for a bad signature, wrong issuer,
    expired token, or any other `PyJWTError` -- one exception type, since
    every one of those means the same thing to a caller: this token does
    not authenticate.
    """
    settings = settings or Settings()
    jwk_client = jwk_client or PyJWKClient(settings.keycloak_workers_jwks_uri)
    try:
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.keycloak_workers_issuer_uri,
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as error:
        raise TokenValidationError(str(error)) from error

    realm_access = payload.get("realm_access", {})
    roles = frozenset(realm_access.get("roles", []))
    return WorkerClaims(subject=payload["sub"], roles=roles)
