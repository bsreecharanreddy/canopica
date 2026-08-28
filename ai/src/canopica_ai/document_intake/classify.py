"""Text extraction + LLM structured classification for one uploaded
document (design doc §2.3, Task 3 plan Steps 2-3).

**Guardrail note (Step 6, not new code):** the document text assembled
here is untrusted, applicant-controlled content (design doc §2.3's
indirect-prompt-injection finding) -- this module has no tool-calling
ability and calls nothing beyond one structured LLM generation, so the
worst an injection can do is corrupt a field's *value*, which the
mandatory worker-confirmation gate (Task 4) catches before it ever reaches
a case record. Nothing here writes anywhere.
"""

from __future__ import annotations

import io
from typing import get_args

import pypdf
import pytesseract
from PIL import Image
from pydantic import BaseModel, Field

from canopica_ai.common.llm_client import OllamaClient, StructuredLlmClient
from canopica_ai.config import Settings
from canopica_ai.document_intake.schema import DocumentType, VerificationDataElement

PROMPT_VERSION = "v1"

# One attempt plus one retry -- same shape and reasoning as rule_authoring's
# own `_MAX_ATTEMPTS`: a single bad sample from a small model is usually
# variance and worth one more roll; two consecutive failures is evidence
# about the request itself.
_MAX_ATTEMPTS = 2

# Prompting guidance only, not an enforced schema -- unlike rule_authoring's
# parameter names (checked against a real list from the database), a
# document's own field names are inherently open-ended, so there is no
# ground truth to validate an extracted name against. Telling the model
# which fields a document of this type usually carries measurably improves
# which fields it looks for, the same reason rule_authoring's own prompt
# spells out the current parameter list in the shape of the JSON it wants
# back, without turning into a hard rejection rule that would penalize a
# document for genuinely having an unanticipated field.
_EXPECTED_FIELDS: dict[DocumentType, tuple[str, ...]] = {
    "INCOME_REPORT": ("employer_name", "gross_monthly_income", "pay_period", "pay_date"),
    "RENEWAL_PACKET": ("household_size", "reported_monthly_income", "signature_date"),
    "WORK_ACTIVITY_REPORT": ("person_name", "weekly_hours", "activity_type", "employer_name"),
    "VERIFICATION_CHECKLIST": ("data_element", "status_claimed", "issuing_source"),
}


class ClassificationError(RuntimeError):
    """The model could not produce a classification/extraction that
    survives schema validation after `_MAX_ATTEMPTS` tries. Raised rather
    than returning a low-confidence guess: an unparseable response isn't a
    low-confidence *extraction*, it's the absence of one, and the worker's
    caller (document_intake_consumer.py) treats this the same as any other
    processing failure -- left for pgmq's own retry, never silently
    swallowed into a fabricated result."""


class _DraftField(BaseModel):
    name: str
    value: str
    confidence: float = Field(ge=0, le=1)


class _DraftExtraction(BaseModel):
    """The model-facing schema. `document_type` is a `Literal`, so Ollama's
    own schema-constrained decoding can only ever pick one of the four real
    types -- there is no path by which this field alone could hallucinate
    a fifth. `likely_data_elements` is similarly constrained to
    `VerificationDataElement`'s real seven values, which is what makes
    `service.py`'s verification-matching step safe to look each one up
    directly against a real `verification.data_element` row rather than
    fuzzy-matching free text."""

    document_type: DocumentType
    fields: list[_DraftField]
    likely_data_elements: list[VerificationDataElement]


def extract_text(content: bytes, content_type: str) -> str:
    """The OCR/text-extraction fallback (Step 2): gets *some* text in
    front of the LLM regardless of upload format, extending only as far as
    this project's pinned generation model (`llama3.2:3b`, text-only) can
    use -- no multimodal page-image path, since there is currently no
    vision-capable model in `Settings` for one to feed. Recorded as a
    scope decision, not an oversight: design doc §2.3's "page images...
    if the LLM client supports multimodal input" is conditional on exactly
    the capability this deployment doesn't have yet.

    - `image/*` (a genuinely scanned upload): Tesseract OCR, the standard,
      real-world first-pass engine for exactly this job.
    - `application/pdf`: `pypdf`'s own text-layer extraction, not OCR --
      this project's synthetic fixtures and the common real-world case are
      both born-digital PDFs with an embedded text layer. A scanned-image
      PDF (no text layer) would extract empty text and fall through to a
      near-zero-confidence result rather than a wrong one, which is the
      safe direction for this to fail in; rendering PDF pages to images
      for a second OCR pass is real, deferred scope (needs `pdf2image` +
      poppler, another system dependency) rather than something silently
      half-done here.
    - anything else: decoded as UTF-8 text directly, replacing anything
      that doesn't decode rather than raising -- a best effort, not a
      guarantee, for whatever content type actually arrives.
    """
    if content_type.startswith("image/"):
        # pytesseract ships no type stubs (pyproject.toml's mypy override),
        # so its return is Any -- narrowed explicitly here rather than
        # letting that Any leak into this function's own str contract.
        return str(pytesseract.image_to_string(Image.open(io.BytesIO(content))))
    if content_type == "application/pdf":
        reader = pypdf.PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return content.decode("utf-8", errors="replace")


def _expected_fields_line(document_type: DocumentType) -> str:
    return ", ".join(_EXPECTED_FIELDS[document_type])


def _classification_prompt(document_text: str) -> str:
    type_guidance = "\n".join(
        f"- {document_type}: typically carries fields like {_expected_fields_line(document_type)}"
        for document_type in _EXPECTED_FIELDS
    )
    return (
        "You are helping a benefits caseworker triage an uploaded document against a SNAP "
        "(food assistance) case. Read the document text below and:\n"
        "1. Classify it as exactly one of: "
        f"{', '.join(_EXPECTED_FIELDS)}.\n"
        "2. Extract every field you can actually find stated in the text, each with a name, "
        "its value as plain text, and a confidence from 0 to 1.\n"
        "3. List which verification data elements (from: "
        f"{', '.join(get_args(VerificationDataElement))}) this document provides evidence for.\n\n"
        "Confidence rules -- these matter more than getting a field at all:\n"
        "- Give a field HIGH confidence (0.8+) only when its value is stated explicitly and "
        "unambiguously in the text.\n"
        "- Give a field LOW confidence (below 0.3) when you are inferring, guessing, or the "
        "text is unclear -- never invent a plausible-looking number and mark it confident.\n"
        "- Never fill a field with a typical, default, or assumed value (for example, "
        'assuming household_size is 1 just because the document does not say otherwise). A '
        "value must come from something the text actually states, never from what a document "
        "of this type usually contains.\n"
        "- If the text does not actually relate to a benefits case at all (e.g. unrelated "
        "correspondence, a greeting, an out-of-office reply), return an empty fields list "
        "rather than guessing a plausible-sounding document type's usual fields.\n"
        "- If the text is too garbled or sparse to extract a field with any real confidence, "
        "omit it rather than guessing.\n\n"
        f"Typical fields per document type, for reference only -- extract what the document "
        f"actually states, not this list:\n{type_guidance}\n\n"
        f"Document text:\n{document_text}\n"
    )


def classify(
    document_text: str,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> _DraftExtraction:
    """One structured LLM call (Step 3), retried once on a malformed
    response. Returns the model-facing draft; `service.py` is what turns
    this into the public `DocumentExtraction` (verification matching,
    provenance)."""
    settings = settings or Settings()
    llm_client = llm_client or OllamaClient(settings)
    prompt = _classification_prompt(document_text)

    last_error: Exception | None = None
    for _ in range(_MAX_ATTEMPTS):
        response = llm_client.generate_structured(prompt, _DraftExtraction)
        try:
            return _DraftExtraction.model_validate_json(response.text)
        except ValueError as error:
            last_error = error
            continue

    raise ClassificationError(
        f"could not classify/extract after {_MAX_ATTEMPTS} attempts: {last_error}"
    )
