"""What `classify_and_extract` hands back to the worker consumer, and what
the consumer then persists into `document.extraction` verbatim (design doc
§2.3): what kind of document this was, what it said, and which of the
case's own outstanding verification checklist items it looks like it
satisfies. Plain snake_case, not `rule_authoring.schema`'s `WireModel` --
nothing here crosses an HTTP boundary yet; Task 4's review-queue endpoint
is what decides how (or whether) this shape gets re-cast for the wire.

Every extraction reaches a worker's review screen before it can touch a
case record (Task 4) -- nothing here is a case-record write path, and
nothing here needs to be. That's what makes this shape simple: unlike
`rule_authoring.schema`, there's no "current value" to diff against and no
unit-domain check to enforce, because nothing downstream of this module
commits a fact on its own say-so.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Roadmap's own list (design doc §2.3): income reports, renewal packets,
# work activity reports, verification-checklist documents.
DocumentType = Literal[
    "INCOME_REPORT", "RENEWAL_PACKET", "WORK_ACTIVITY_REPORT", "VERIFICATION_CHECKLIST"
]

# Mirrors `verification.data_element`'s own CHECK constraint (V9 migration)
# exactly -- the classification step proposes matches only from this set,
# never a free-text guess, so a proposed match can always be looked up
# against a real `verification` row's own column.
VerificationDataElement = Literal[
    "IDENTITY",
    "RESIDENCY",
    "INCOME",
    "SHELTER_COST",
    "MEDICAL_EXPENSE",
    "DISABILITY",
    "HOUSEHOLD_COMPOSITION",
]


class ExtractedField(BaseModel):
    """One field the model read off the document. `confidence` is what
    drives Task 4's review-queue ordering and per-field visual emphasis --
    it never decides whether a human sees this field, only how urgently
    (design doc §2.3's "confidence-gated review, no auto-apply bypass")."""

    name: str
    value: str
    confidence: float = Field(ge=0, le=1)


class DocumentExtraction(BaseModel):
    """What `service.classify_and_extract` returns -- the sole interface
    the worker consumer calls (Task 3 plan's own Interfaces note). Carries
    its own provenance for the same reason `ParameterProposal` and
    `PolicyQaAnswerRecord` do: a figure that may end up in a case record
    has to be traceable to which model, under which prompt, produced it."""

    document_type: DocumentType
    fields: list[ExtractedField]
    matched_verification_ids: list[UUID]
    generation_model: str
    prompt_version: str
