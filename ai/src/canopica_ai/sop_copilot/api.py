"""FastAPI surface for the Caseworker SOP Copilot -- what
`HttpSopCopilotClient` (the API service's Java caller) actually calls over
HTTP, same one-capability-per-FastAPI-app shape `policy_intelligence.qa.api`
already uses.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from canopica_ai.sop_copilot.service import SopAnswer, ask

app = FastAPI(title="Canopica SOP Copilot")


class AskRequest(BaseModel):
    question: str


@app.post("/sop-copilot/ask")
def ask_endpoint(request: AskRequest) -> SopAnswer:
    return ask(request.question)
