"""PII tokenization vault (design doc §2.3, Phase 1b Task 7).

dim_person.sql (Task 10) already keeps names out of gold, but it does so
with a one-way sha256 hash -- adequate for "don't expose it," not enough
for "recover it under a real, audited need" (a correction to a
misspelled name, an access-review investigation). This module replaces
that hash with an opaque, vault-backed, *reversible* token: the same real
value always resolves to the same token (get_or_create_token), and the
real value can be recovered from a token only through a separate, explicit
call (detokenize) -- never a normal column read.

date_of_birth/address are deliberately left alone here. dim_person already
stores birth_year only (never the full date) and dim_household already
drops the street address entirely rather than carrying it into silver at
all -- both a stronger data-minimization posture than tokenization would
add, and neither has a downstream consumer that would ever need to recover
the original value. See docs/design/2026-08-22-phase-1b-hardening-design.md's
Task 7 correction note for the full reasoning.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import psycopg
from deltalake import write_deltalake

NAME = "NAME"


def _value_hash(real_value: str) -> str:
    return hashlib.sha256(real_value.encode()).hexdigest()


def get_or_create_token(
    conn: psycopg.Connection, real_value: str, value_type: str, encryption_key: str
) -> str:
    """Idempotent: the same (real_value, value_type) pair always returns the
    same token, without ever inserting a second vault row for it."""
    value_hash = _value_hash(real_value)
    with conn.cursor() as cur:
        cur.execute(
            "select token from pii_token where value_type = %s and value_hash = %s",
            (value_type, value_hash),
        )
        row = cur.fetchone()
        if row is not None:
            return str(row[0])

        token = f"tok_{value_type.lower()}_{secrets.token_hex(16)}"
        cur.execute(
            "insert into pii_token (token, value_hash, encrypted_value, value_type) "
            "values (%s, %s, pgp_sym_encrypt(%s, %s), %s)",
            (token, value_hash, real_value, encryption_key, value_type),
        )
    return token


def detokenize(conn: psycopg.Connection, token: str, encryption_key: str) -> str:
    """Recovers the real value behind a token. Raises rather than returning
    None for an unknown token -- "no value" and "no such token" are
    different, more alarming, facts for whoever is auditing this call."""
    with conn.cursor() as cur:
        cur.execute(
            "select pgp_sym_decrypt(encrypted_value, %s) from pii_token where token = %s",
            (encryption_key, token),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"unknown token: {token}")
    return str(row[0])


def tokenize_person_names(
    dsn: str,
    bronze_root: Path,
    encryption_key: str,
    *,
    batch_id: uuid.UUID | None = None,
) -> int:
    """Tokenizes every person's (first_name, last_name) pair into the vault
    and lands a bronze Delta table of person_id -> name_token pairs.
    dim_person.sql (silver) joins against this instead of hashing the name
    inline -- same "bronze holds what silver reads" shape as every other
    bronze table, just produced by this module instead of a verbatim
    operational-table copy, since a token doesn't exist until this step
    creates it. Runs before `dbt build` in the pipeline, same as
    extract_to_bronze. Returns the number of person rows tokenized.
    """
    resolved_batch_id = str(batch_id or uuid.uuid4())
    ingested_at = datetime.now(UTC)

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("select id, first_name, last_name from person")
            rows = cur.fetchall()

        records = [
            {
                "person_id": str(person_id),
                "name_token": get_or_create_token(
                    conn, f"{first_name}|{last_name}".lower(), NAME, encryption_key
                ),
            }
            for person_id, first_name, last_name in rows
        ]

    frame = pl.DataFrame(records, schema={"person_id": pl.Utf8, "name_token": pl.Utf8})
    frame = frame.with_columns(
        pl.lit(ingested_at).alias("_ingested_at"),
        pl.lit("person_pii_tokens").alias("_source_table"),
        pl.lit(resolved_batch_id).alias("_batch_id"),
    )
    write_deltalake(str(bronze_root / "person_pii_tokens"), frame.to_arrow(), mode="append")
    return len(records)
