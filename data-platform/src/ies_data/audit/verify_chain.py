"""Walk the audit chain and recompute every hash.

Run standalone in CI:
    uv run python -m ies_data.audit.verify_chain --dsn "$IES_OPERATIONAL_DSN"

Exit code 1 on a broken chain, so a workflow step fails the build.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass

import psycopg

ZERO_HASH = "0" * 64


@dataclass(frozen=True)
class ChainVerification:
    """Result of walking the audit chain from the first row to the last."""

    rows_checked: int
    ok: bool
    first_bad_id: int | None


def verify_chain(dsn: str) -> ChainVerification:
    """Recompute every audit_event hash in id order and compare to what's stored.

    The tail material and its ordering mirror the V6 migration's
    audit_event_chain() trigger exactly -- this function and that trigger
    must never disagree about what gets hashed.
    """
    previous = ZERO_HASH
    checked = 0
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            select id, prev_hash, hash,
                   to_char(occurred_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.USOF')
                     || event_type || actor_id || subject_type
                     || subject_id::text || payload::text as tail
            from audit_event
            order by id
            """
        )
        for row_id, prev_hash, stored_hash, tail in cur:
            expected = hashlib.sha256((previous + tail).encode("utf-8")).hexdigest()
            if prev_hash != previous or stored_hash != expected:
                return ChainVerification(checked, False, row_id)
            previous = stored_hash
            checked += 1
    return ChainVerification(checked, True, None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the IES audit hash chain.")
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()

    result = verify_chain(args.dsn)
    print(f"audit chain: {result.rows_checked} rows checked, ok={result.ok}")
    if not result.ok:
        print(f"chain broken at audit_event.id = {result.first_bad_id}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
