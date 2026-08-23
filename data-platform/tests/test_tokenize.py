"""Integration tests for the PII tokenization vault (Task 7) -- needs a
real Postgres instance with the V11 migration's pii_token table and
pgcrypto extension, since the point is proving real encrypt/decrypt round
trips, not a mocked shape."""

import os
import subprocess
from pathlib import Path

import duckdb
import psycopg
import pytest
from deltalake import DeltaTable

from canopica_data.governance.tokenize import (
    detokenize,
    get_or_create_token,
    tokenize_person_names,
)
from canopica_data.ingestion.extract import ALL_TABLES, extract_to_bronze

DATA_PLATFORM_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = DATA_PLATFORM_ROOT / "dbt" / "canopica_warehouse"
TEST_ENCRYPTION_KEY = "test-pii-vault-key"


@pytest.mark.integration
def test_get_or_create_token_round_trips(migrated_dsn: str) -> None:
    with psycopg.connect(migrated_dsn, autocommit=True) as conn:
        conn.execute("truncate table pii_token")
        token = get_or_create_token(conn, "jane|doe", "NAME", TEST_ENCRYPTION_KEY)
        recovered = detokenize(conn, token, TEST_ENCRYPTION_KEY)

    assert recovered == "jane|doe"
    assert token != "jane|doe"


@pytest.mark.integration
def test_get_or_create_token_is_idempotent(migrated_dsn: str) -> None:
    with psycopg.connect(migrated_dsn, autocommit=True) as conn:
        conn.execute("truncate table pii_token")
        first = get_or_create_token(conn, "jane|doe", "NAME", TEST_ENCRYPTION_KEY)
        second = get_or_create_token(conn, "jane|doe", "NAME", TEST_ENCRYPTION_KEY)

        row = conn.execute(
            "select count(*) from pii_token where value_type = 'NAME'"
        ).fetchone()

    assert first == second
    assert row is not None
    assert row[0] == 1


@pytest.mark.integration
def test_detokenize_unknown_token_raises(migrated_dsn: str) -> None:
    with psycopg.connect(migrated_dsn, autocommit=True) as conn:
        conn.execute("truncate table pii_token")
        with pytest.raises(ValueError, match="unknown token"):
            detokenize(conn, "tok_name_does-not-exist", TEST_ENCRYPTION_KEY)


@pytest.mark.integration
def test_tokenize_person_names_lands_a_token_per_person(
    seeded_operational_dsn: str, tmp_path: Path
) -> None:
    count = tokenize_person_names(seeded_operational_dsn, tmp_path / "bronze", TEST_ENCRYPTION_KEY)

    # Must match conftest.py's seeded_operational_dsn fixture, which seeds
    # this many person rows per invocation.
    assert count == 3
    table = DeltaTable(str(tmp_path / "bronze" / "person_pii_tokens")).to_pyarrow_table()
    assert table.num_rows == 3
    assert {"person_id", "name_token", "_ingested_at"} <= set(table.column_names)


@pytest.mark.integration
def test_dim_person_stores_tokens_not_raw_names(
    seeded_operational_dsn: str, tmp_path: Path
) -> None:
    """Proves the actual wiring, end to end: after a real dbt build,
    dim_person.name_token isn't shaped like a name, and detokenizing it
    recovers the exact operational-database value for that person -- the
    same standard test_tokenize_a_round_trips proves at the vault level,
    re-checked here through the real silver model."""
    warehouse_root = tmp_path
    duckdb_path = tmp_path / "canopica.duckdb"
    extract_to_bronze(seeded_operational_dsn, warehouse_root / "bronze", list(ALL_TABLES))
    tokenize_person_names(seeded_operational_dsn, warehouse_root / "bronze", TEST_ENCRYPTION_KEY)

    result = subprocess.run(
        [
            "dbt",
            "build",
            "--project-dir",
            str(DBT_PROJECT_DIR),
            "--profiles-dir",
            str(DBT_PROJECT_DIR),
            "--target",
            "local",
        ],
        cwd=DATA_PLATFORM_ROOT,
        env={
            **os.environ,
            "CANOPICA_WAREHOUSE_ROOT": str(warehouse_root),
            "CANOPICA_DUCKDB_PATH": str(duckdb_path),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        person_rows = con.execute(
            "select person_key, name_token from main_silver.dim_person"
        ).fetchall()
    finally:
        con.close()

    assert len(person_rows) == 3
    with psycopg.connect(seeded_operational_dsn, autocommit=True) as conn:
        for person_key, name_token in person_rows:
            assert not name_token.startswith("Person")  # not the raw first_name
            operational = conn.execute(
                "select first_name, last_name from person where id = %s", (person_key,)
            ).fetchone()
            assert operational is not None
            expected = f"{operational[0]}|{operational[1]}".lower()
            assert detokenize(conn, name_token, TEST_ENCRYPTION_KEY) == expected
