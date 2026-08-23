-- pgcrypto already enabled by V6 (audit_event's chain hashing) -- IF NOT
-- EXISTS makes re-declaring it here safe and self-documenting for this
-- migration's own purpose too.
create extension if not exists pgcrypto;

create table pii_token (
    token           text        primary key,
    -- sha256 of the real value, used only to look up an existing token
    -- idempotently. pgp_sym_encrypt's own ciphertext is intentionally
    -- non-deterministic (a fresh session key per call), so it cannot serve
    -- as a lookup key itself -- this column is the deliberate workaround.
    value_hash      char(64)    not null,
    encrypted_value bytea       not null,
    value_type      text        not null check (value_type in ('NAME', 'DATE_OF_BIRTH', 'ADDRESS')),
    created_at      timestamptz not null default now(),
    constraint pii_token_value_unique unique (value_type, value_hash)
);

-- Detokenization is a separate, audited, narrowly-granted read (design doc
-- §2.3) -- not the general silver/reporting access every other table gets.
-- This single-role local demo has only one application role (ies_app,
-- which owns this table via the migration and so keeps full access
-- regardless), so there is no second role to narrow the grant to yet;
-- revoking from public documents and enforces the intended default for any
-- role added later rather than leaving it implicitly wide open. See
-- docs/design/compliance-mapping.md for the real-deployment equivalent.
revoke all on pii_token from public;
