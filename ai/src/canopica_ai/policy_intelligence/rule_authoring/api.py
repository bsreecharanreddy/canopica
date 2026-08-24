"""FastAPI surface for the rule-authoring copilot -- what the Java portal's
`PolicyParameterPublishService` calls over HTTP.

The first portal -> AI direction in this system (Task 2's Q&A calls the
other way), which is why the boundary is drawn where it is: the portal owns
the database and the publish decision, and asks this service only for a
draft it is free to reject.

Routes are declared on an `APIRouter` and mounted on a module-level `app`,
so this is independently runnable today (`uvicorn
canopica_ai.policy_intelligence.rule_authoring.api:app`) and mountable into one
combined application when Task 9's hosted demo needs a single origin --
without either capability having to move.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import Field

from canopica_ai.policy_intelligence.rule_authoring.schema import (
    CurrentParameter,
    ParameterProposal,
    WireModel,
)
from canopica_ai.policy_intelligence.rule_authoring.service import (
    ProposalGenerationError,
    propose_parameter_changes,
)

router = APIRouter(prefix="/rule-authoring", tags=["rule-authoring"])


class ProposeRequest(WireModel):
    """`currentValues` is the caller's job to supply, not this service's to
    look up -- see `propose_parameter_changes` for why that boundary is
    where it is."""

    document_excerpt: str = Field(min_length=1)
    current_parameter_set_id: UUID
    current_values: list[CurrentParameter] = Field(min_length=1)


@router.post("/propose")
def propose(request: ProposeRequest) -> ParameterProposal:
    try:
        return propose_parameter_changes(
            request.document_excerpt,
            request.current_parameter_set_id,
            request.current_values,
        )
    except ProposalGenerationError as error:
        # 502, not 500: the copilot ran and declined to produce something it
        # could stand behind. That is a normal outcome for an excerpt this
        # small model cannot read, and the portal shows it to the admin as
        # such rather than treating it as an outage.
        raise HTTPException(status_code=502, detail=str(error)) from error


app = FastAPI(title="Canopica Rule-authoring copilot")
app.include_router(router)
