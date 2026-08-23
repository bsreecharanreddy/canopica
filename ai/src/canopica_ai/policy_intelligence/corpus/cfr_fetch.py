"""Fetches the real, public 7 CFR Part 273 section text this project's
rules engine implements, from eCFR's public Versioner API, and caches it
under ``corpus/raw/`` (committed -- a portfolio project's corpus should be
reproducible without a live network call on every ``make up``).

    uv run python -m canopica_ai.policy_intelligence.corpus.cfr_fetch
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

# Pinned to a specific CFR annual-edition date so re-running this script is
# reproducible against the same government text version, not "whatever
# eCFR currently shows." Title 7 is revised annually as of January 1.
CFR_AS_OF_DATE = "2026-01-01"
CFR_TITLE = "7"
CFR_PART = "273"

# The sections this project's rules engine
# (rules-engine/src/main/resources/dmn/snap-eligibility.dmn) actually
# implements -- gross/net income tests and the standard/earned-income/
# dependent-care/medical/shelter deductions live in 273.9; expedited
# service and categorical eligibility live in 273.2 (design doc §2.1's
# scoping). chunk.py further narrows each of these down to the specific
# paragraphs in scope.
TARGET_SECTIONS = ("273.2", "273.9")

RAW_DIR = Path(__file__).parent / "raw"


def fetch_section(section: str) -> str:
    """Fetches one section's full text, as real eCFR XML, for CFR_AS_OF_DATE."""
    url = f"https://www.ecfr.gov/api/versioner/v1/full/{CFR_AS_OF_DATE}/title-{CFR_TITLE}.xml"
    response = httpx.get(
        url,
        params={"part": CFR_PART, "section": section},
        headers={"User-Agent": "canopica-ai-corpus-fetch/0.1 (portfolio project)"},
        timeout=30.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for section in TARGET_SECTIONS:
        text = fetch_section(section)
        out_path = RAW_DIR / f"{section}.xml"
        out_path.write_text(text, encoding="utf-8")
        print(f"{section}: {len(text)} bytes -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
