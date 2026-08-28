"""Document classification & extraction (design doc §2.3).

Two layers, the same split test_rule_authoring.py already established:
`TestExtractText` and `TestClassifyGuardRails` below drive real OCR/PDF
parsing and a stub LLM, and run on every push with no Ollama/MinIO/Postgres
required. The `e2e`-marked class at the bottom is the one that needs the
real stack -- it asks whether the pipeline can actually read a document
end to end (MinIO fetch, OCR/PDF text extraction, a real model call,
verification matching against real Postgres rows), which no stub can
answer.
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import date
from typing import Any
from uuid import UUID

import boto3
import psycopg
import pytest
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from canopica_ai.common.llm_client import LlmResponse
from canopica_ai.config import Settings
from canopica_ai.document_intake.classify import ClassificationError, classify, extract_text
from canopica_ai.document_intake.service import classify_and_extract


def _minimal_pdf_bytes(text: str) -> bytes:
    """Hand-built rather than loaded from a fixture file: a valid,
    minimal, one-page PDF whose only content is a `Tj` text-show operator
    -- enough for pypdf's own text extraction to read back, without a
    second PDF-authoring dependency (reportlab) just to produce a test
    input."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 300 300] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 18 Tf 10 150 Td ({text}) Tj ET".encode()
    objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_start = out.tell()
    n = len(objects) + 1
    out.write(f"xref\n0 {n}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode())
    return out.getvalue()


def _text_image_bytes(text: str) -> bytes:
    image = Image.new("RGB", (500, 120), color="white")
    draw = ImageDraw.Draw(image)
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except OSError:
        # CI's runner has no macOS system fonts -- Tesseract copes far
        # better with a real scalable font than its own tiny bitmap
        # default, but a correct extraction from *some* font matters more
        # here than which one.
        font = ImageFont.load_default()
    draw.text((10, 40), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class TestExtractText:
    """Step 2's OCR/text-extraction fallback -- real Tesseract, real
    pypdf, no LLM involved."""

    def test_a_scanned_image_upload_is_read_via_real_ocr(self) -> None:
        content = _text_image_bytes("INCOME 2100 DOLLARS")
        text = extract_text(content, "image/png")
        # Tesseract against a rendered font is not pixel-perfect, so this
        # checks for the one detail that actually matters to the pipeline
        # (the figure), not an exact transcription of the whole line.
        assert "2100" in text

    def test_a_born_digital_pdf_is_read_via_its_own_text_layer(self) -> None:
        content = _minimal_pdf_bytes("Employer Acme Corp")
        text = extract_text(content, "application/pdf")
        assert "Acme Corp" in text

    def test_an_unrecognized_content_type_falls_back_to_utf8_decoding(self) -> None:
        text = extract_text(b"household size 3", "text/plain")
        assert text == "household size 3"


class _StubStructuredClient:
    """Same shape test_rule_authoring.py's own stub takes: returns canned
    raw JSON strings in order, one per call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate_structured(self, prompt: str, schema: type[BaseModel]) -> LlmResponse:
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("stub called more times than the test staged responses for")
        return LlmResponse(text=self._responses.pop(0))


def _draft_json(
    document_type: str = "INCOME_REPORT",
    fields: list[dict[str, Any]] | None = None,
    likely_data_elements: list[str] | None = None,
) -> str:
    if fields is None:
        fields = [{"name": "gross_monthly_income", "value": "2100", "confidence": 0.9}]
    if likely_data_elements is None:
        likely_data_elements = ["INCOME"]
    return json.dumps(
        {
            "document_type": document_type,
            "fields": fields,
            "likely_data_elements": likely_data_elements,
        }
    )


class TestClassifyGuardRails:
    """What `classify()` does with what the model hands back."""

    def test_a_valid_response_becomes_a_draft(self) -> None:
        draft = classify("some document text", llm_client=_StubStructuredClient([_draft_json()]))

        assert draft.document_type == "INCOME_REPORT"
        [field] = draft.fields
        assert field.name == "gross_monthly_income"
        assert field.confidence == pytest.approx(0.9)
        assert draft.likely_data_elements == ["INCOME"]

    def test_a_malformed_response_is_retried_once(self) -> None:
        draft = classify(
            "some document text",
            llm_client=_StubStructuredClient(["not valid json", _draft_json()]),
        )
        assert draft.document_type == "INCOME_REPORT"

    def test_two_consecutive_malformed_responses_raise(self) -> None:
        with pytest.raises(ClassificationError):
            classify(
                "some document text",
                llm_client=_StubStructuredClient(["not valid json", "still not valid json"]),
            )

    def test_a_document_type_outside_the_known_four_is_rejected_and_retried(self) -> None:
        # A real Ollama call can't produce this (document_type is a
        # Literal, constrained at the sampler) -- this exercises the
        # schema-validation layer directly, standing in for a
        # non-compliant/adversarial model response.
        bad_response = _draft_json(document_type="MEDICAL_RECORD")
        with pytest.raises(ClassificationError):
            classify(
                "some document text",
                llm_client=_StubStructuredClient([bad_response, bad_response]),
            )

    def test_a_field_confidence_outside_zero_to_one_is_rejected(self) -> None:
        with pytest.raises(ClassificationError):
            classify(
                "some document text",
                llm_client=_StubStructuredClient(
                    [
                        _draft_json(fields=[{"name": "x", "value": "y", "confidence": 1.5}]),
                        _draft_json(fields=[{"name": "x", "value": "y", "confidence": 1.5}]),
                    ]
                ),
            )


def _seed_outstanding_income_verification(settings: Settings) -> tuple[UUID, UUID]:
    """A minimal person -> household -> application -> program_request
    chain plus one OUTSTANDING income verification, inserted directly via
    SQL against the real local Postgres (assumed migrated -- this is the
    e2e tier, same "make up already ran" convention this file's own
    docstring states). Returns (program_request_id, verification_id)."""
    person_id, household_id, application_id, program_request_id, verification_id = (
        uuid.uuid4() for _ in range(5)
    )
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into person (id, first_name, last_name, date_of_birth, ssn_token, sex) "
            "values (%s, 'Sam', 'Applicant', '1990-01-01', %s, 'F')",
            (person_id, f"ssn-token-{person_id}"),
        )
        cur.execute(
            "insert into household "
            "(id, head_person_id, county, address_line1, city, state, zip_code) "
            "values (%s, %s, 'Test County', '1 Test St', 'Testville', 'TS', '00000')",
            (household_id, person_id),
        )
        cur.execute(
            "insert into application (id, household_id, submitted_at, channel) "
            "values (%s, %s, now(), 'ONLINE')",
            (application_id, household_id),
        )
        cur.execute(
            "insert into program_request (id, application_id, program_code, status, requested_on) "
            "values (%s, %s, 'SNAP', 'PENDING_VERIFICATION', %s)",
            (program_request_id, application_id, date.today()),
        )
        cur.execute(
            "insert into verification (id, program_request_id, data_element, status, due_on) "
            "values (%s, %s, 'INCOME', 'OUTSTANDING', %s)",
            (verification_id, program_request_id, date.today()),
        )
    return program_request_id, verification_id


def _upload_fixture(
    settings: Settings, program_request_id: UUID, content: bytes, content_type: str
) -> str:
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        region_name="us-east-1",
    )
    object_key = f"{program_request_id}/{uuid.uuid4()}"
    s3.put_object(
        Bucket=settings.minio_bucket, Key=object_key, Body=content, ContentType=content_type
    )
    return object_key


@pytest.mark.e2e
class TestClassifyAndExtractAgainstARealStack:
    """The tests here that need Ollama, MinIO, and a migrated Postgres:
    whether the pipeline can actually read a document and propose the
    right verification match, and whether it stays honest about a document
    that doesn't give it enough to go on."""

    def test_a_clear_income_report_extracts_the_figure_and_matches_the_outstanding_verification(
        self, settings: Settings
    ) -> None:
        program_request_id, verification_id = _seed_outstanding_income_verification(settings)
        content = (
            b"PAY STATEMENT\n"
            b"Employer: Acme Corp\n"
            b"Employee: Sam Applicant\n"
            b"Pay period: monthly\n"
            b"Gross monthly income: $2,100.00\n"
        )
        object_key = _upload_fixture(settings, program_request_id, content, "text/plain")

        extraction = classify_and_extract(object_key, "text/plain", settings=settings)

        assert extraction.document_type == "INCOME_REPORT"
        values_by_name = {field.name: field.value for field in extraction.fields}
        assert any("2100" in value or "2,100" in value for value in values_by_name.values())
        assert verification_id in extraction.matched_verification_ids

    def test_an_ambiguous_document_produces_low_confidence_rather_than_a_confident_guess(
        self, settings: Settings
    ) -> None:
        program_request_id, _ = _seed_outstanding_income_verification(settings)
        # Deliberately sparse and off-topic: nothing here actually states an
        # income figure, a household size, or an activity -- design doc
        # §2.3's own bar is that this must not produce a confident wrong
        # answer, whatever it does produce.
        content = b"Thank you for your recent inquiry. We will be in touch."
        object_key = _upload_fixture(settings, program_request_id, content, "text/plain")

        extraction = classify_and_extract(object_key, "text/plain", settings=settings)

        assert all(field.confidence < 0.5 for field in extraction.fields)
