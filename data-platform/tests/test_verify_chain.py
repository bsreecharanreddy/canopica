"""Integration tests for the audit-chain verifier -- needs a real Postgres
instance with the actual V6 migration's trigger applied, since the whole
point is proving this Python code and that SQL trigger agree on what gets
hashed."""

from collections.abc import Callable

import pytest

from ies_data.audit.verify_chain import verify_chain


@pytest.mark.integration
def test_verifies_an_untampered_chain(seeded_audit_dsn: str) -> None:
    result = verify_chain(seeded_audit_dsn)

    assert result.ok
    assert result.rows_checked == 5
    assert result.first_bad_id is None


@pytest.mark.integration
def test_detects_a_tampered_payload(
    seeded_audit_dsn: str, as_superuser: Callable[[str], None]
) -> None:
    # Disabling the trigger and editing a row directly is only possible as a
    # superuser -- exactly the scenario this verifier exists to catch, since
    # no application-level control could have prevented it either.
    as_superuser("alter table audit_event disable trigger audit_event_no_mutation")
    as_superuser('update audit_event set payload = \'{"tampered": true}\'::jsonb where id = 3')

    result = verify_chain(seeded_audit_dsn)

    assert not result.ok
    assert result.first_bad_id == 3
