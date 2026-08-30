"""The one LLM call this capability makes (design doc §2.3): drafting a
plain-language discrepancy explanation for a QC reviewer. Every dollar
figure is given to the model in the prompt, never computed by it
(constraint 21) -- `validate.py`'s own deterministic check catches a
figure the model invents that doesn't trace back to the real diff or
either evaluation's own trace. Same retry-once-on-malformed-response shape
`correspondence/draft.py` already establishes.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from canopica_ai.common.llm_client import OllamaClient, StructuredLlmClient
from canopica_ai.config import Settings

PROMPT_VERSION = "v1"

# Same "one retry is worth it, two is evidence" reasoning document_intake's
# own classify.py and correspondence's own draft.py already apply.
_MAX_ATTEMPTS = 2


class SummaryDraftError(RuntimeError):
    """The model could not produce a schema-valid summary after
    `_MAX_ATTEMPTS` tries. Raised rather than falling back to a canned
    string -- an unexplained discrepancy is a real processing failure,
    left for pgmq's own retry, same posture `correspondence.draft.
    ExplanationDraftError` already establishes."""


class DiscrepancyContext(BaseModel):
    """Everything the prompt and `validate.py`'s own grounding check are
    grounded in, bundled into one object rather than six-plus positional
    parameters -- `service.py` is what assembles this from `_fetch_traces`
    and the caller-supplied amounts."""

    original_amount: Decimal
    reproduced_amount: Decimal
    error_amount: Decimal
    original_trace: dict[str, Any]
    reproduced_trace: dict[str, Any]
    policy_parameter_version: str


class _DraftSummary(BaseModel):
    summary: str


def _summary_prompt(context: DiscrepancyContext) -> str:
    return (
        "You are drafting a one-to-three sentence plain-language explanation for a SNAP Quality "
        "Control reviewer, describing why re-deriving a past benefit decision from its own stored "
        "facts produced a different monthly amount than what was originally recorded. The reviewer "
        "already sees the raw numbers -- your only job is to explain what changed between the two "
        "evaluations.\n\n"
        f"Originally recorded monthly amount: ${context.original_amount}\n"
        f"Re-derived monthly amount: ${context.reproduced_amount}\n"
        f"Difference (re-derived minus original): ${context.error_amount}\n"
        f"Policy parameter set version both evaluations resolved against: "
        f"{context.policy_parameter_version}\n\n"
        "Every named decision value from the ORIGINAL evaluation's own trace, in evaluation "
        f"order:\n{context.original_trace}\n\n"
        "Every named decision value from the RE-DERIVED evaluation's own trace, in evaluation "
        f"order:\n{context.reproduced_trace}\n\n"
        "Rules that matter more than sounding polished:\n"
        "- Use ONLY the dollar amounts given above. Never introduce a number that isn't already "
        "stated there, and never compute a new one yourself.\n"
        "- Point to which named decision value actually differs between the two traces, if any "
        "does -- that is the real cause. If nothing differs, say the amounts still don't match "
        "without inventing a cause.\n"
        "- Plain language, no jargon, no legal citations.\n"
    )


def draft_summary(
    context: DiscrepancyContext,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> str:
    """One structured LLM call, retried once on a malformed response.
    Returns the summary text only -- `service.py`'s own deterministic
    grounding check (`validate.py`) is what decides whether it's trusted,
    not this function."""
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)
    prompt = _summary_prompt(context)

    last_error: Exception | None = None
    for _ in range(_MAX_ATTEMPTS):
        response = llm_client.generate_structured(prompt, _DraftSummary)
        try:
            return _DraftSummary.model_validate_json(response.text).summary
        except ValueError as error:
            last_error = error
            continue

    raise SummaryDraftError(
        f"could not draft a discrepancy summary after {_MAX_ATTEMPTS} attempts: {last_error}"
    )
