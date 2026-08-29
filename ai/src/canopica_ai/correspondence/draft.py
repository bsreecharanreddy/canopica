"""The one LLM call this capability makes (design doc §2.4's central
mechanism decision): filling the plain-language *explanation* slot only.
Every dollar amount, date, and program name in the notice is substituted
programmatically by `service.py` from `DeterminationRecord` itself -- the
model never drafts the notice's structure or its numbers, only the prose
explaining a decision that is already made and already correct.

**Guardrail note (design doc §2.9, not new code):** the only untrusted
input this prompt carries is `DeterminationRecord.household_head_name`
(applicant-supplied at intake) -- everything else is this system's own
computed trace. The worst a name-based injection could do is corrupt the
prose the model writes, which `validate.py`'s own deterministic number/
date check still catches before a human ever reviews it, since that check
runs on the *whole* filled template, explanation included.
"""

from __future__ import annotations

from pydantic import BaseModel

from canopica_ai.common.llm_client import OllamaClient, StructuredLlmClient
from canopica_ai.config import Settings
from canopica_ai.correspondence.schema import DeterminationRecord, NoticeType

PROMPT_VERSION = "v1"

# Same "one retry is worth it, two is evidence" reasoning document_intake's
# own classify.py already applies.
_MAX_ATTEMPTS = 2

# Task 7 (design doc §2.5): the model drafts the explanation directly in
# the target language -- never an English draft translated after the
# fact -- so there is exactly one LLM output to run through validate.py's
# deterministic check, in either language. Keys match `schema.
# SUPPORTED_LANGUAGES`.
_LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}


class ExplanationDraftError(RuntimeError):
    """The model could not produce a schema-valid explanation after
    `_MAX_ATTEMPTS` tries. Raised rather than falling back to a canned
    string -- an unexplained notice is a real processing failure, left for
    pgmq's own retry, not silently papered over (same posture document_
    intake.classify.ClassificationError already establishes)."""


class _DraftExplanation(BaseModel):
    explanation: str


def _explanation_prompt(
    notice_type: NoticeType, determination: DeterminationRecord, language: str
) -> str:
    language_name = _LANGUAGE_NAMES[language]
    return (
        "You are drafting the plain-language explanation paragraph for a SNAP "
        f"(food assistance) {notice_type.replace('_', ' ').lower()} notice. The decision itself is "
        "already final -- your only job is to explain, in 2-4 plain sentences a household member "
        "can understand, why it came out this way.\n\n"
        f"Decision: {'ELIGIBLE' if determination.eligible else 'NOT ELIGIBLE'}\n"
        f"Reason code: {determination.reason_code}\n"
        f"Monthly benefit amount: ${determination.benefit_amount}\n\n"
        "Every figure the decision was actually based on, from this case's own calculation trace "
        "(a dict of named values in the order they were evaluated):\n"
        f"{determination.trace_decisions}\n\n"
        "Rules that matter more than sounding polished:\n"
        "- Use ONLY the dollar amounts and dates given above or in the trace. Never introduce a "
        "number, date, or figure that isn't already stated there -- if you cannot explain the "
        "decision without a figure you were not given, describe it in words instead (for example, "
        '"your household\'s income" rather than inventing a dollar amount).\n'
        "- Do not restate the benefit amount as a heading -- the notice template already shows it "
        "separately. Focus on the *why*.\n"
        "- Plain language, no jargon, no legal citations.\n"
        f"- Write the explanation in {language_name}. Every dollar amount and date must still be "
        "copied verbatim, digits and format unchanged, from what's given above -- translate the "
        "surrounding words only, never a number.\n"
    )


def draft_explanation(
    notice_type: NoticeType,
    determination: DeterminationRecord,
    *,
    language: str = "en",
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> str:
    """One structured LLM call, retried once on a malformed response.
    Returns the explanation paragraph only, drafted directly in
    `language` (design doc §2.5: a translated draft is generated through
    this *same* function, parameterized by target language, never a
    separate less-reviewed path) -- `service.py` is what substitutes it
    (and every numeric/date slot) into the chosen template."""
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)
    prompt = _explanation_prompt(notice_type, determination, language)

    last_error: Exception | None = None
    for _ in range(_MAX_ATTEMPTS):
        response = llm_client.generate_structured(prompt, _DraftExplanation)
        try:
            return _DraftExplanation.model_validate_json(response.text).explanation
        except ValueError as error:
            last_error = error
            continue

    raise ExplanationDraftError(
        f"could not draft an explanation after {_MAX_ATTEMPTS} attempts: {last_error}"
    )
