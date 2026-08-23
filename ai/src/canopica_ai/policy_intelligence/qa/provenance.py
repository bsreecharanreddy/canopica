"""Persists every Policy Q&A answer (design doc §2.2's provenance
paragraph): not just the answer text, but exactly what produced it --
corpus/embedding/prompt/model versions and retrieval config -- so "why did
the system say this" is reconstructible after the fact, the same bar Phase
1a's determination trace already clears for a benefit amount.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
from pydantic import BaseModel

from canopica_ai.config import Settings


class PolicyQaAnswerRecord(BaseModel):
    question: str
    answer: str
    citations: list[str]
    abstained: bool
    corpus_version: str
    embedding_model_version: str
    retrieval_config: dict[str, Any]
    prompt_version: str
    retrieved_chunk_ids: list[str]
    # Null for an abstained answer: no LLM call was made at all.
    generation_model: str | None = None
    generation_params: dict[str, Any] | None = None
    # Set only for the "why was I denied" path.
    determination_id: str | None = None


def record(data: PolicyQaAnswerRecord, *, settings: Settings | None = None) -> str:
    """Inserts one row into `ai.policy_qa_answer`, returning its id."""
    settings = settings or Settings()
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into ai.policy_qa_answer (
                question, answer, citations, abstained, corpus_version,
                embedding_model_version, retrieval_config, prompt_version,
                generation_model, generation_params, retrieved_chunk_ids,
                determination_id
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                data.question,
                data.answer,
                data.citations,
                data.abstained,
                data.corpus_version,
                data.embedding_model_version,
                json.dumps(data.retrieval_config),
                data.prompt_version,
                data.generation_model,
                json.dumps(data.generation_params) if data.generation_params is not None else None,
                data.retrieved_chunk_ids,
                data.determination_id,
            ),
        )
        row = cur.fetchone()
        assert row is not None
        return str(row[0])
