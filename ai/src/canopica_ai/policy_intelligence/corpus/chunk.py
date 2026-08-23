"""Splits the raw, cached 7 CFR text (cfr_fetch.py) into citation-grade
subsection chunks -- one OpenSearch document per chunk, each carrying the
exact CFR citation a "why was I denied" answer can point at.

**Why explicit top-level anchors, not a fully generic marker parser**:
eCFR's full-text XML is a flat list of sibling ``<P>`` elements per
section -- no attribute records nesting depth, and a paragraph's own
leading marker (``(a)``, ``(1)``, ``(i)``, ``(A)``) is the only structural
signal available. A first implementation tried the obvious general
parser -- track the last-opened letter and treat a paragraph as opening a
new one only when its marker is the *next expected* letter in sequence --
and it silently mis-chunks this project's own real corpus: 7 CFR 273.2(h)
opens its own sub-list directly at a bare roman numeral ``(i)`` with no
numbered level in between, and single-character tokens (``i``, ``v``,
``x``, ``l``, ``c``, ``d``, ``m``) are simultaneously valid roman numerals
*and* valid next-letters, so that parser reads 273.2(h)'s roman ``(i)`` as
if it were a new top-level paragraph -- then folds the *real*, separate
"(i) Expedited service" paragraph (appearing later) into that unrelated
one as trailing text, corrupting exactly the citation this corpus exists
to get right. Given the actual corpus is a small, bounded set of
sections, each top-level chunk's start anchor is instead hand-verified
once against the real fetched text, below.

**Why chunks also get recursively subdivided by size**: a hand-verified
top-level paragraph can still be far larger than Ollama's embedding model
context window (nomic-embed-text: a real, hard ~2048-token ceiling hit
during implementation on 273.2(j) categorical eligibility, ~6,500 tokens
in one paragraph). Below that ceiling, digit markers are unambiguous
(never collide with letters or roman numerals), so ``_subdivide`` below
recurses on real digit/roman/upper-letter markers -- still the CFR's own
subsection structure, not an arbitrary fixed-token window -- until every
chunk fits.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# defusedxml, not stdlib xml.etree, to parse this untrusted-by-origin
# government text safely (XXE/entity-expansion hardening) -- returns the
# same Element API, so .findall()/.itertext() below are unaffected.
from defusedxml import ElementTree as DefusedElementTree

RAW_DIR = Path(__file__).parent / "raw"

# A soft target, not a hard ceiling: most chunks land well under this once
# split at real CFR marker boundaries, with margin against nomic-embed-
# text's actual ~2048-token context limit (roughly 3-4 characters/token
# for English legal text). A few chunks with no further real marker level
# available (_subdivide's level_index exhausted) stay above it -- verified
# individually against the real embedding model at implementation time
# rather than assumed safe from this constant alone.
MAX_CHUNK_CHARS = 3500

_NUMBER_MARKER = re.compile(r"^\((\d+)\)\s*")
_ROMAN_MARKER = re.compile(r"^\(([ivxlcdm]+)\)\s*")
_UPPER_MARKER = re.compile(r"^\(([A-Z]+)\)\s*")
_HEADING_RE = re.compile(r"^\([\w]+\)\s*(.+?)(?:[.—]|$)")

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman_to_int(marker: str) -> int | None:
    total, previous = 0, 0
    for char in reversed(marker):
        value = _ROMAN_VALUES.get(char)
        if value is None:
            return None
        total += value if value >= previous else -value
        previous = max(previous, value)
    return total


def _upper_to_int(marker: str) -> int | None:
    return ord(marker) - ord("A") + 1 if len(marker) == 1 else None


@dataclass(frozen=True)
class ChunkBoundary:
    """One top-level subsection's start anchor: the exact, verified-unique
    leading text of the ``<P>`` that opens it.

    ``include=False`` marks a boundary that exists only to cap the
    *previous* included chunk's span at the right place (an out-of-scope
    paragraph sitting between two included ones) -- it never becomes a
    chunk of its own.
    """

    start_anchor: str
    cfr_section: str = ""
    heading: str = ""
    include: bool = True


# Verified against the real corpus/raw/*.xml (fetched by cfr_fetch.py for
# CFR_AS_OF_DATE) at implementation time -- each start_anchor is checked to
# occur exactly where expected, in document order, per section below.
# (d)'s own numbered sub-items (standard/earned-income/medical/dependent-
# care/child-support/shelter deductions) are not individually anchored
# here -- digit markers are unambiguous, so _subdivide's automatic
# number-level split below produces them; (5) optional child support is
# filtered out by number afterward instead (see chunk_section).
SECTION_BOUNDARIES: dict[str, list[ChunkBoundary]] = {
    "273.9": [
        ChunkBoundary(
            "(a) Income eligibility standards", "273.9(a)", "Income eligibility standards"
        ),
        ChunkBoundary("(b) Definition of income.", include=False),
        ChunkBoundary("(c) Income exclusions.", include=False),
        # No paragraph (e) exists in 273.9 -- shelter costs, (d)'s last
        # numbered item, is also the section's last paragraph, so this
        # boundary has no following one and runs to end of document.
        ChunkBoundary("(d) Income deductions.", "273.9(d)", "Income deductions"),
    ],
    "273.2": [
        ChunkBoundary("(i) Expedited service", "273.2(i)", "Expedited service"),
        ChunkBoundary(
            "(j) PA, GA and categorically eligible households.",
            "273.2(j)",
            "Categorical eligibility",
        ),
        ChunkBoundary("(k) SSI households.", include=False),
    ],
}

# (d)'s own numbered items excluded from the corpus scope by design (design
# doc §2.1: only the standard/earned-income/dependent-care/medical/shelter
# deductions, not every deduction 273.9(d) happens to list).
_EXCLUDED_SUBSECTIONS = frozenset({"273.9(d)(5)"})


@dataclass(frozen=True)
class CfrChunk:
    cfr_section: str
    heading: str
    text: str


def _paragraph_texts(xml_text: str) -> list[str]:
    root = DefusedElementTree.fromstring(xml_text)
    return ["".join(p.itertext()).strip() for p in root.findall("P")]


def _derive_heading(first_paragraph: str, fallback: str) -> str:
    match = _HEADING_RE.match(first_paragraph)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return fallback


def _split_sequential(
    paragraphs: list[str],
    marker_re: re.Pattern[str],
    to_ordinal: Callable[[str], int | None],
) -> list[tuple[str | None, list[str]]]:
    """Splits paragraphs into (marker, group) pairs, opening a new group
    only when a paragraph's leading marker is exactly one more (per
    ``to_ordinal``) than the last-opened marker at this same level,
    starting from 1.

    Real CFR lists restart their numbering at 1 (or "i", or "A") within
    *every* new nested list, not just once per section -- e.g.
    273.9(d)(6)'s own shelter-cost provisions contain several independent
    ``(1)(2)(3)...`` lists nested under different roman-numeral/
    upper-letter parents, and 273.2(i)/(j) similarly re-use roman numerals
    at multiple nesting depths. A plain "any marker of this type matches"
    scan would treat every one of those restarts as a fresh sibling of
    whatever group is genuinely open at this level (a real bug hit during
    implementation, on exactly this corpus). Requiring strict "+1 from
    here" sequencing means a later, unrelated restart can never match once
    the real sequence has moved on, so it correctly falls through as
    continuation text instead.
    """
    groups: list[tuple[str | None, list[str]]] = []
    current_marker: str | None = None
    current_value = 0
    current: list[str] = []
    for paragraph in paragraphs:
        match = marker_re.match(paragraph)
        value = to_ordinal(match.group(1)) if match else None
        if value is not None and value == current_value + 1:
            if current:
                groups.append((current_marker, current))
            current_marker = match.group(1)  # type: ignore[union-attr]
            current_value = value
            current = [paragraph]
        elif current:
            current.append(paragraph)
        else:
            current = [paragraph]
    if current:
        groups.append((current_marker, current))
    return groups


# Each level's marker pattern paired with how to compute its numeric
# position for sequential validation (see _split_sequential).
_LEVELS: tuple[tuple[re.Pattern[str], Callable[[str], int | None]], ...] = (
    (_NUMBER_MARKER, int),
    (_ROMAN_MARKER, _roman_to_int),
    (_UPPER_MARKER, _upper_to_int),
)


def _subdivide(
    cfr_section: str, heading: str, paragraphs: list[str], level_index: int = 0
) -> list[CfrChunk]:
    """Recursively splits an oversized paragraph group at successive
    marker levels -- digit, then roman numeral, then upper-letter (the
    only levels unambiguous once already inside a single hand-verified
    top-level paragraph -- see the module docstring).

    ``level_index`` strictly increases on every recursive call, whether or
    not that level actually produced a split -- a level is tried *at most
    once per branch*, never retried deeper in the same branch. Combined
    with ``_split_sequential``'s own +1-only rule, this is the fix for a
    real bug hit during implementation: a plain "any marker of this type"
    scan, retried from the top at every call, let digit- and roman-marked
    lists nested deep inside 273.9(d)(6)'s shelter-cost provisions and
    273.2(i)/(j)'s own sub-lists get mistaken for fresh siblings of their
    real top-level parents, since CFR markers restart within every new
    nested list, not just once per section.
    """
    text = " ".join(paragraphs).strip()
    if len(text) <= MAX_CHUNK_CHARS or level_index >= len(_LEVELS):
        return [CfrChunk(cfr_section=cfr_section, heading=heading, text=text)]

    marker_re, to_ordinal = _LEVELS[level_index]
    groups = _split_sequential(paragraphs, marker_re, to_ordinal)
    if len(groups) <= 1:
        # This level's marker type isn't present here -- CFR nesting
        # sometimes skips a level (e.g. letter directly to roman, no
        # number in between), so try the next deeper level on the same,
        # still-unsplit paragraphs rather than giving up.
        return _subdivide(cfr_section, heading, paragraphs, level_index + 1)

    chunks: list[CfrChunk] = []
    for marker, group in groups:
        sub_section = f"{cfr_section}({marker})" if marker else cfr_section
        sub_heading = _derive_heading(group[0], heading) if marker else heading
        chunks.extend(_subdivide(sub_section, sub_heading, group, level_index + 1))
    return chunks


def chunk_section(xml_text: str, section_number: str) -> list[CfrChunk]:
    """Splits one section's raw XML into its scoped subsection chunks,
    per ``SECTION_BOUNDARIES[section_number]``."""
    boundaries = SECTION_BOUNDARIES[section_number]
    paragraphs = _paragraph_texts(xml_text)

    starts: list[int] = []
    search_from = 0
    for boundary in boundaries:
        found = next(
            (
                i
                for i in range(search_from, len(paragraphs))
                if paragraphs[i].startswith(boundary.start_anchor)
            ),
            None,
        )
        if found is None:
            raise ValueError(
                f"chunk anchor not found in {section_number}: {boundary.start_anchor!r}"
            )
        starts.append(found)
        search_from = found + 1

    chunks: list[CfrChunk] = []
    for position, boundary in enumerate(boundaries):
        if not boundary.include:
            continue
        start = starts[position]
        end = starts[position + 1] if position + 1 < len(starts) else len(paragraphs)
        chunks.extend(_subdivide(boundary.cfr_section, boundary.heading, paragraphs[start:end]))

    return [c for c in chunks if c.cfr_section not in _EXCLUDED_SUBSECTIONS]


def load_all_chunks() -> list[CfrChunk]:
    """Loads every section's raw XML from ``corpus/raw/`` (cfr_fetch.py's
    committed output) and returns the full scoped chunk set, in
    ``SECTION_BOUNDARIES``'s own section order."""
    chunks: list[CfrChunk] = []
    for section_number in SECTION_BOUNDARIES:
        xml_text = (RAW_DIR / f"{section_number}.xml").read_text(encoding="utf-8")
        chunks.extend(chunk_section(xml_text, section_number))
    return chunks
