"""FastAPI app for the public hosted demo (Task 9 plan, Step 4) -- Policy
Q&A's general-question path only, no login. Wraps `answer_general()` with
Step 2's guardrails and Step 3's rate limiter, and configures it for
`inference_mode=public_demo` (Step 1's `OpenRouterTieredClient`) -- this
is the only place in the codebase all four pieces meet.

"Why was I denied" needs an authenticated citizen's own determination and
stays behind login (design doc §2.7) -- deliberately not reachable here.

`_get_llm_client`/`_get_rate_limiter` are `lru_cache`-memoized, not built
at import time: `OpenRouterTieredClient.__init__` requires
`CANOPICA_OPENROUTER_API_KEY`, and the plain `ai` CI job (`pytest -m "not
e2e"`, no OpenRouter key set at all) collects every test module including
this one's -- an eager construction would break that job's test
collection over a dependency it has no reason to need. Tests monkeypatch
the getter functions themselves before either is ever called for real.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from canopica_ai.common.guardrails import GuardrailBlockedError, check_input, check_output
from canopica_ai.common.llm_client import InferenceUnavailableError, LlmClient, build_llm_client
from canopica_ai.common.rate_limit import RateLimitExceededError, SessionRateLimiter
from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.qa.service import QaAnswer, answer_general

_SESSION_COOKIE = "canopica_demo_session"
_GENERIC_REFUSAL_MESSAGE = (
    "This demo can only answer general questions about SNAP eligibility policy."
)
_UNAVAILABLE_MESSAGE = "This demo is temporarily unavailable -- please try again shortly."

_STATIC_DIR = Path(__file__).parent / "static"


@lru_cache(maxsize=1)
def _get_settings() -> Settings:
    return Settings(inference_mode="public_demo")


@lru_cache(maxsize=1)
def _get_llm_client() -> LlmClient:
    return build_llm_client(_get_settings())


@lru_cache(maxsize=1)
def _get_rate_limiter() -> SessionRateLimiter:
    return SessionRateLimiter(_get_settings())


router = APIRouter()


class AskRequest(BaseModel):
    question: str


@router.post("/demo/ask")
def ask(request: AskRequest, http_request: Request, response: Response) -> QaAnswer:
    session_id = http_request.cookies.get(_SESSION_COOKIE) or str(uuid.uuid4())
    response.set_cookie(_SESSION_COOKIE, session_id, httponly=True, samesite="lax")

    try:
        _get_rate_limiter().check_and_increment(session_id)
    except RateLimitExceededError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error

    llm_client = _get_llm_client()

    try:
        check_input(request.question, llm_client)
    except GuardrailBlockedError as error:
        raise HTTPException(status_code=400, detail=_GENERIC_REFUSAL_MESSAGE) from error

    try:
        answer = answer_general(
            request.question,
            settings=_get_settings(),
            llm_client=llm_client,
            record_provenance=False,
        )
    except InferenceUnavailableError as error:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE_MESSAGE) from error

    try:
        check_output(request.question, answer.answer, llm_client)
    except GuardrailBlockedError as error:
        raise HTTPException(status_code=400, detail=_GENERIC_REFUSAL_MESSAGE) from error

    return answer


app = FastAPI(title="Canopica public demo")
app.include_router(router)
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
