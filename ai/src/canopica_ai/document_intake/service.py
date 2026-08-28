"""Document classification & extraction (Task 3 plan): the sole interface
the worker's `document_intake_consumer.py` calls. Fetches the object from
MinIO, runs `classify.py`'s text-extraction + LLM classification, matches
the result against the case's own outstanding verification checklist, and
returns a `DocumentExtraction` -- never writes anywhere itself. Same split
`rule_authoring` holds: this module drafts, the worker (like the API
elsewhere) is what actually persists anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import boto3
import psycopg

# mypy-boto3-s3 (via ai/pyproject.toml's boto3-stubs[s3]) is a type-stub-only
# dev dependency, never installed at runtime -- worker/pyproject.toml's own
# path dependency on this package only pulls its real `dependencies`, so an
# unconditional import here would break the one caller that actually
# matters (the worker). Deferred to type-checking only; `from __future__
# import annotations` above already keeps every annotation unevaluated at
# runtime, so nothing below needs the real class at import time.
if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

from canopica_ai.common.llm_client import StructuredLlmClient
from canopica_ai.common.observability import traced_ai_operation
from canopica_ai.config import Settings
from canopica_ai.document_intake.classify import PROMPT_VERSION, classify, extract_text
from canopica_ai.document_intake.schema import DocumentExtraction, ExtractedField


def _program_request_id(object_key: str) -> UUID:
    """`object_key` is always `{programRequestId}/{documentId}`
    (`DocumentService.java`'s own construction, design doc §2.1) -- parsed
    back out here rather than threaded through as a separate parameter, so
    this interface stays exactly the two fields the Task 3 plan states."""
    program_request_id, _, _ = object_key.partition("/")
    return UUID(program_request_id)


def _build_s3_client(settings: Settings) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        region_name="us-east-1",
    )


def _fetch_object(s3_client: S3Client, bucket: str, object_key: str) -> bytes:
    response = s3_client.get_object(Bucket=bucket, Key=object_key)
    return response["Body"].read()


def _matched_verification_ids(
    program_request_id: UUID, likely_data_elements: list[str], *, settings: Settings
) -> list[UUID]:
    """Direct read-only Postgres query, same boundary `qa/provenance.py`
    already uses for case-domain data -- this service has no write access
    of its own, and a query is not a mutation. Matches only outstanding
    verifications whose own `data_element` is one the model proposed,
    never a free-text guess against the checklist."""
    if not likely_data_elements:
        return []
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "select id from verification "
            "where program_request_id = %s and status = 'OUTSTANDING' and data_element = any(%s)",
            (program_request_id, likely_data_elements),
        )
        return [row[0] for row in cur.fetchall()]


def classify_and_extract(
    object_key: str,
    content_type: str,
    *,
    settings: Settings | None = None,
    llm_client: StructuredLlmClient | None = None,
    s3_client: S3Client | None = None,
) -> DocumentExtraction:
    """Fetches the uploaded object, extracts its text, classifies it, and
    proposes which outstanding verification(s) it satisfies. Never writes
    to `document`, `verification`, or the audit log -- that's the worker
    consumer's own job, once a human confirms (Task 4)."""
    settings = settings or Settings()
    s3_client = s3_client or _build_s3_client(settings)
    program_request_id = _program_request_id(object_key)

    with traced_ai_operation("document_intake.classify_and_extract"):
        content = _fetch_object(s3_client, settings.minio_bucket, object_key)
        document_text = extract_text(content, content_type)
        draft = classify(document_text, settings=settings, llm_client=llm_client)
        matched_verification_ids = _matched_verification_ids(
            program_request_id, list(draft.likely_data_elements), settings=settings
        )

    return DocumentExtraction(
        document_type=draft.document_type,
        fields=[
            ExtractedField(name=field.name, value=field.value, confidence=field.confidence)
            for field in draft.fields
        ],
        matched_verification_ids=matched_verification_ids,
        generation_model=settings.ollama_generation_model,
        prompt_version=PROMPT_VERSION,
    )
