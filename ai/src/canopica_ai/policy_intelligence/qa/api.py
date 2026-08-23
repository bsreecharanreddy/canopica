"""FastAPI surface for Policy Q&A -- what `PolicyQaPage.tsx` and Task 9's
public demo actually call over HTTP.
"""

from __future__ import annotations

from fastapi import FastAPI, Header
from pydantic import BaseModel, ConfigDict, Field

from canopica_ai.policy_intelligence.qa.service import QaAnswer, answer_denial, answer_general

app = FastAPI(title="Canopica Policy Q&A")


class AskRequest(BaseModel):
    question: str


class WhyWasIDeniedRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # camelCase on the wire, matching the rest of this system's JSON
    # convention (the portal API's own Jackson defaults), even though
    # Python's own attribute is snake_case.
    determination_id: str = Field(alias="determinationId")


@app.post("/qa/ask")
def ask(request: AskRequest) -> QaAnswer:
    return answer_general(request.question)


@app.post("/qa/why-was-i-denied")
def why_was_i_denied(request: WhyWasIDeniedRequest, authorization: str = Header(...)) -> QaAnswer:
    """Forwards the citizen's own bearer token to the portal's trace
    endpoint server-side (see `answer_denial`) -- this service never
    receives a token it can use for anything beyond that one read."""
    bearer_token = authorization.removeprefix("Bearer ").strip()
    return answer_denial(request.determination_id, bearer_token)
