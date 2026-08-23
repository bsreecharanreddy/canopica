"""Creates the CFR corpus OpenSearch index and bulk-indexes every scoped
chunk (chunk.py), embedding each chunk's text via Ollama.

Idempotent by delete-and-recreate: corpus size is small and this only runs
at ingestion time, not per request, so this is simpler and safer than
diffing against an existing index.

    uv run python -m canopica_ai.policy_intelligence.corpus.index
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch, helpers

from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.corpus.chunk import CfrChunk, load_all_chunks
from canopica_ai.policy_intelligence.retrieval import embed_text

# ai/src/canopica_ai/policy_intelligence/corpus/index.py -> repo root -> infra/opensearch
MAPPING_PATH = (
    Path(__file__).resolve().parents[5] / "infra" / "opensearch" / "cfr_index_mapping.json"
)


def _build_documents(chunks: list[CfrChunk], settings: Settings) -> list[dict[str, Any]]:
    documents = []
    for chunk in chunks:
        embedding = embed_text(chunk.text, settings)
        documents.append(
            {
                "_index": settings.cfr_corpus_index,
                "_id": chunk.cfr_section,
                "_source": {
                    "cfr_section": chunk.cfr_section,
                    "heading": chunk.heading,
                    "text": chunk.text,
                    "embedding": embedding,
                },
            }
        )
    return documents


def index_corpus(client: OpenSearch, settings: Settings) -> int:
    """(Re)creates the corpus index from cfr_index_mapping.json and bulk-
    indexes every chunk from chunk.load_all_chunks(). Returns the number of
    documents indexed."""
    if client.indices.exists(index=settings.cfr_corpus_index):
        client.indices.delete(index=settings.cfr_corpus_index)

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    mapping["mappings"]["properties"]["embedding"]["dimension"] = settings.embedding_dimension
    client.indices.create(index=settings.cfr_corpus_index, body=mapping)

    documents = _build_documents(load_all_chunks(), settings)
    success, errors = helpers.bulk(client, documents, refresh="wait_for")
    if errors:
        raise RuntimeError(f"bulk indexing errors: {errors}")
    return int(success)


def main() -> None:
    settings = Settings()
    client = OpenSearch(hosts=[settings.opensearch_url])
    count = index_corpus(client, settings)
    print(f"indexed {count} chunks into {settings.cfr_corpus_index!r}", file=sys.stderr)


if __name__ == "__main__":
    main()
