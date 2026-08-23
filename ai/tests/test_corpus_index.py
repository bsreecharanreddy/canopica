"""Tests for chunk.py (pure) and the live OpenSearch index (integration).

The pure chunking tests run against the real, committed raw XML under
corpus/raw/ -- not a synthetic fixture -- so they prove this project's
actual corpus parses correctly, not just that the algorithm works on
contrived input.
"""

from __future__ import annotations

import pytest
from opensearchpy import OpenSearch

from canopica_ai.config import Settings
from canopica_ai.policy_intelligence.corpus.chunk import RAW_DIR, chunk_section, load_all_chunks


def _load_raw(section: str) -> str:
    return (RAW_DIR / f"{section}.xml").read_text(encoding="utf-8")


def test_chunk_section_273_9_produces_one_chunk_per_deduction_type() -> None:
    chunks = chunk_section(_load_raw("273.9"), "273.9")
    sections = {c.cfr_section for c in chunks}

    assert "273.9(a)" in sections
    for expected in ("273.9(d)(1)", "273.9(d)(2)", "273.9(d)(3)", "273.9(d)(4)"):
        assert expected in sections
    # Shelter costs, (d)'s largest and last numbered item, is oversized
    # enough to recursively subdivide further (see chunk.py's module
    # docstring) -- assert its own top-level chunk exists as one of the
    # resulting pieces, not that it's the *only* one.
    assert any(s.startswith("273.9(d)(6)") for s in sections)
    assert "273.9(d)(5)" not in sections  # excluded: optional child support


def test_chunk_section_273_9_every_chunk_fits_the_embedding_context_budget() -> None:
    chunks = chunk_section(_load_raw("273.9"), "273.9")

    # Real ceiling is nomic-embed-text's ~2048-token context window (hit
    # during implementation on an earlier, unsplit shelter-deduction
    # chunk); this is a generous char-count proxy for it, not the exact
    # boundary -- see chunk.py's MAX_CHUNK_CHARS comment.
    for chunk in chunks:
        assert len(chunk.text) < 8000, f"{chunk.cfr_section} is {len(chunk.text)} chars"


def test_chunk_section_273_9_partition_is_lossless() -> None:
    """Every real paragraph in the scoped (a)/(d) spans ends up in exactly
    one chunk -- recursive subdivision must never drop or duplicate text."""
    chunks = chunk_section(_load_raw("273.9"), "273.9")
    sections = [c.cfr_section for c in chunks]

    assert len(sections) == len(set(sections))  # no id produced twice
    # A phrase from deep inside the shelter-cost provisions that a earlier,
    # buggy version of this splitter either lost or duplicated onto an
    # unrelated deduction chunk (see chunk.py's module docstring).
    needle = "individual standard for each type of utility expense"
    matches = [c for c in chunks if needle in c.text]
    assert len(matches) == 1
    assert matches[0].cfr_section.startswith("273.9(d)(6)")


def test_chunk_section_273_9_excludes_income_definition_and_exclusions() -> None:
    chunks = chunk_section(_load_raw("273.9"), "273.9")

    full_text = " ".join(c.text for c in chunks)
    assert "Definition of income" not in full_text
    assert "Optional child support deduction" not in full_text


def test_chunk_section_273_9_shelter_deduction_runs_to_end_of_section() -> None:
    chunks = chunk_section(_load_raw("273.9"), "273.9")
    shelter_chunks = [c for c in chunks if c.cfr_section.startswith("273.9(d)(6)")]

    assert any("Shelter costs" in c.text for c in shelter_chunks)
    # The section's own last paragraph (a nested utility-allowance
    # provision several levels deep under shelter costs) must be captured
    # *somewhere* under this deduction, proving the split runs to the true
    # end of the document rather than an accidental early cutoff -- not
    # necessarily in the top (d)(6) chunk itself, since recursive
    # subdivision (chunk.py's own module docstring) may have carried it
    # into a deeper sibling.
    assert any("shares heating or cooling expenses" in c.text for c in shelter_chunks)


def test_chunk_section_273_2_isolates_expedited_service_from_a_letter_roman_collision() -> None:
    """273.2(h) opens its own sub-list directly at a bare roman-numeral
    "(i)" with no numbered level between them -- the same character as the
    real, separate "(i) Expedited service" paragraph appearing later. A
    naive "next expected letter" parser folds Expedited Service's real
    text into that unrelated (h) sub-item; this asserts the real corpus
    text is chunked correctly despite that collision."""
    chunks = chunk_section(_load_raw("273.2"), "273.2")
    expedited_chunks = [c for c in chunks if c.cfr_section.startswith("273.2(i)")]

    assert any("Expedited service" in c.text for c in expedited_chunks)
    assert any("Entitlement to expedited service" in c.text for c in expedited_chunks)
    unrelated = "delay shall be considered the fault of the household"
    assert not any(unrelated in c.text for c in expedited_chunks)


def test_chunk_section_273_2_categorical_eligibility_stops_before_next_letter() -> None:
    chunks = chunk_section(_load_raw("273.2"), "273.2")

    categorical = next(c for c in chunks if c.cfr_section == "273.2(j)")
    assert "categorically eligible" in categorical.text
    # (k)'s own opening sentence, defining SSI for *that* paragraph's own
    # purposes -- distinct from (j)'s legitimate mentions of SSI recipients
    # as one categorical-eligibility pathway.
    unrelated = "For purposes of this paragraph, SSI is defined as Federal SSI payments"
    assert unrelated not in categorical.text


def test_chunk_section_raises_on_missing_anchor() -> None:
    with pytest.raises(ValueError, match="anchor not found"):
        chunk_section("<DIV8><P>nothing relevant here</P></DIV8>", "273.9")


def test_load_all_chunks_covers_every_scoped_section() -> None:
    chunks = load_all_chunks()

    sections = {c.cfr_section for c in chunks}
    assert len(sections) == len(chunks)  # every id unique across sections too
    assert "273.9(a)" in sections
    assert "273.2(j)" in sections
    # Every chunk has real, non-trivial text and a human-readable heading --
    # not just a citation with nothing behind it.
    for chunk in chunks:
        assert len(chunk.text) > 50
        assert chunk.heading


@pytest.mark.e2e
class TestLiveCorpusIndex:
    """Needs the real OpenSearch + Ollama from `make up` (see conftest.py's
    indexed_corpus fixture) -- proves the actual index this project ships,
    not just the pure chunking logic above."""

    def test_index_exists_with_expected_document_count(
        self, indexed_corpus: Settings, opensearch_client: OpenSearch
    ) -> None:
        count_response = opensearch_client.count(index=indexed_corpus.cfr_corpus_index)

        assert count_response["count"] == len(load_all_chunks())

    def test_a_known_section_round_trips_exactly(
        self, indexed_corpus: Settings, opensearch_client: OpenSearch
    ) -> None:
        expected = next(c for c in load_all_chunks() if c.cfr_section == "273.9(a)")

        document = opensearch_client.get(index=indexed_corpus.cfr_corpus_index, id="273.9(a)")

        assert document["_source"]["cfr_section"] == "273.9(a)"
        assert document["_source"]["heading"] == expected.heading
        assert document["_source"]["text"] == expected.text
        assert len(document["_source"]["embedding"]) == indexed_corpus.embedding_dimension
