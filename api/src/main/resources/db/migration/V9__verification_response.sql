-- The mock external verification interface's raw response (design doc §2.2).
-- `verification` itself (V2) is a status/tracking row with no field for a
-- payload -- this is the genuinely new part, kept off `verification.status`
-- so that column's existing OUTSTANDING/RECEIVED/WAIVED CHECK constraint
-- doesn't need touching.
create table verification_response (
    id                  uuid primary key,
    verification_id     uuid        not null references verification (id),
    outcome              text        not null check (outcome in ('MATCHES', 'DISCREPANCY', 'UNAVAILABLE')),
    raw_payload          jsonb       not null,
    received_at          timestamptz not null default now()
);
create index verification_response_verification_idx on verification_response (verification_id);
