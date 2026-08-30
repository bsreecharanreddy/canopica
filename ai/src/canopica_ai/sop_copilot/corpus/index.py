"""Creates the SOP corpus OpenSearch index and bulk-indexes every chunk
(chunk.py), embedding each chunk's text via Ollama. Structurally mirrors
`policy_intelligence/corpus/index.py` -- same idempotent delete-and-
recreate posture, same embed-then-bulk-index shape -- pointed at a
separate index (`settings.sop_corpus_index`) so SOP and policy retrieval
never cross-contaminate (Phase 4 Task 7 plan).

    uv run python -m canopica_ai.sop_copilot.corpus.index
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch, helpers

from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.retrieval import embed_text
from canopica_ai.sop_copilot.corpus.chunk import SopChunk, load_all_chunks

# ai/src/canopica_ai/sop_copilot/corpus/index.py -> repo root -> infra/opensearch
MAPPING_PATH = (
    Path(__file__).resolve().parents[5] / "infra" / "opensearch" / "sop_index_mapping.json"
)


def _build_documents(chunks: list[SopChunk], settings: Settings) -> list[dict[str, Any]]:
    documents = []
    for i, chunk in enumerate(chunks):
        embedding = embed_text(chunk.text, settings)
        documents.append(
            {
                "_index": settings.sop_corpus_index,
                "_id": f"{chunk.document}#{i}",
                "_source": {
                    "document": chunk.document,
                    "heading": chunk.heading,
                    "text": chunk.text,
                    "embedding": embedding,
                },
            }
        )
    return documents


def index_corpus(client: OpenSearch, settings: Settings) -> int:
    """(Re)creates the SOP index from sop_index_mapping.json and bulk-
    indexes every chunk from chunk.load_all_chunks(). Returns the number
    of documents indexed."""
    if client.indices.exists(index=settings.sop_corpus_index):
        client.indices.delete(index=settings.sop_corpus_index)

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    mapping["mappings"]["properties"]["embedding"]["dimension"] = settings.embedding_dimension
    client.indices.create(index=settings.sop_corpus_index, body=mapping)

    documents = _build_documents(load_all_chunks(), settings)
    success, errors = helpers.bulk(client, documents, refresh="wait_for")
    if errors:
        raise RuntimeError(f"bulk indexing errors: {errors}")
    return int(success)


def main() -> None:
    settings = Settings()
    client = OpenSearch(hosts=[settings.opensearch_url])
    count = index_corpus(client, settings)
    print(f"indexed {count} chunks into {settings.sop_corpus_index!r}", file=sys.stderr)


if __name__ == "__main__":
    main()
