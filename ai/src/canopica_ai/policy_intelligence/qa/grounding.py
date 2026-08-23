"""Deterministic citation-grounding pre-check (design doc §2.6): a cheap,
zero-noise check kept from an earlier draft, run before Task 7's LLM-judged
RAGAS/DeepEval metrics -- catches a fabricated citation for free, without
spending a judge call on it.
"""

from __future__ import annotations


def citation_grounded(answer_citations: list[str], retrieved_chunk_ids: list[str]) -> bool:
    """True only if every citation the answer emits corresponds to a chunk
    actually retrieved for this query. An answer with no citations at all is
    not grounded -- it isn't citing fabricated text, but it also isn't
    citing the material it was supposedly given, which this check treats
    the same way: not proven grounded.
    """
    if not answer_citations:
        return False
    return all(citation in retrieved_chunk_ids for citation in answer_citations)
