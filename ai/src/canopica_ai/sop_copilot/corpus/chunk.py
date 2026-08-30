"""Splits an authored SOP markdown document into one chunk per `##`-level
section -- structurally mirrors `policy_intelligence/corpus/chunk.py`'s
job (turn a source document into citation-grade retrieval chunks), but a
far simpler split: these documents are authored directly for this corpus
(see `corpus/README.md`), not fetched/parsed regulation XML with
irregular nested markers, so a flat heading split is the real structure,
not a simplification of something more complex.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CORPUS_DIR = Path(__file__).parent

# One doc = one file stem, used as the `document` field every chunk from
# that file carries -- e.g. "new_application" for new_application.md.
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class SopChunk:
    document: str
    heading: str
    text: str


def chunk_document(document: str, markdown_text: str) -> list[SopChunk]:
    """Splits on `##` headings; the `#`-level title line (if any) is
    dropped -- it names the document, not a citable section within it."""
    matches = list(_HEADING_RE.finditer(markdown_text))
    chunks: list[SopChunk] = []
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        text = markdown_text[start:end].strip()
        chunks.append(SopChunk(document=document, heading=heading, text=text))
    return chunks


def load_all_chunks() -> list[SopChunk]:
    """Loads every `*.md` file directly under `corpus/` (excluding
    README.md, which documents the corpus rather than being part of it)
    and returns the full chunk set, alphabetical by file name."""
    chunks: list[SopChunk] = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        if path.stem.lower() == "readme":
            continue
        chunks.extend(chunk_document(path.stem, path.read_text(encoding="utf-8")))
    return chunks
