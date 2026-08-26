create extension if not exists pgcrypto;

create table audit_event (
    id              bigserial primary key,
    occurred_at     timestamptz not null default now(),
    event_type      text        not null check (event_type in
                        ('APPLICATION_SUBMITTED', 'DETERMINATION_MADE',
                         'CASE_VIEWED', 'VERIFICATION_UPDATED')),
    actor_id        text        not null,
    subject_type    text        not null,
    subject_id      uuid        not null,
    payload         jsonb       not null,
    prev_hash       char(64)    not null,
    hash            char(64)    not null
);

-- The chain is computed in the database, in a trigger, under a transaction-
-- scoped advisory lock. The application supplies the payload and nothing
-- else: it cannot choose, skip, or backdate a hash.
--
-- jsonb::text is canonical in Postgres (keys sorted, whitespace normalized),
-- so the hashed string is stable across clients and drivers.
create or replace function audit_event_chain() returns trigger
language plpgsql as $$
declare
    last_hash char(64);
    material  text;
begin
    perform pg_advisory_xact_lock(hashtext('canopica.audit_event'));

    select hash into last_hash from audit_event order by id desc limit 1;
    new.prev_hash := coalesce(last_hash, repeat('0', 64));

    material := new.prev_hash
        || to_char(new.occurred_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.USOF')
        || new.event_type || new.actor_id || new.subject_type
        || new.subject_id::text || new.payload::text;

    new.hash := encode(digest(material, 'sha256'), 'hex');
    return new;
end;
$$;

create trigger audit_event_chain_before_insert
    before insert on audit_event
    for each row execute function audit_event_chain();

create or replace function audit_event_is_append_only() returns trigger
language plpgsql as $$
begin
    raise exception 'audit_event is append-only (attempted %)', tg_op;
end;
$$;

create trigger audit_event_no_mutation
    before update or delete on audit_event
    for each row execute function audit_event_is_append_only();

-- Defence in depth: the trigger stops the owner; the grant stops everyone
-- else. ${app_role} is substituted by Flyway from spring.flyway.placeholders,
-- so the grant applies to the role the application actually connects as.
revoke update, delete on audit_event from public;
revoke update, delete on audit_event from ${app_role};
grant insert, select on audit_event to ${app_role};

create index audit_event_subject_idx on audit_event (subject_type, subject_id);
