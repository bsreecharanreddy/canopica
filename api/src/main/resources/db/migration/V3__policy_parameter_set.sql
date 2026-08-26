create table policy_parameter_set (
    id                  uuid primary key,
    program_code        text        not null check (program_code in ('SNAP')),
    version_label       text        not null unique,        -- e.g. 'SNAP-FY2025'
    effective_from      date        not null,
    effective_to        date,                                -- null = still in force
    source_citation     text        not null,                -- title + URL of the published memo
    retrieved_on        date        not null,
    published_at        timestamptz not null default now(),
    constraint policy_parameter_set_effective_range check (effective_to is null or effective_to >= effective_from),
    constraint policy_parameter_set_unique_span unique (program_code, effective_from)
);

create table policy_parameter (
    id                  uuid primary key,
    parameter_set_id    uuid        not null references policy_parameter_set (id),
    name                text        not null,
    -- null household_size = the parameter is scalar (a rate, a threshold);
    -- non-null = the value applies to exactly that household size.
    household_size      integer     check (household_size is null or household_size between 1 and 8),
    numeric_value       numeric(12, 4) not null,
    unit                text        not null check (unit in ('USD_PER_MONTH', 'RATE', 'COUNT')),
    constraint policy_parameter_unique unique (parameter_set_id, name, household_size)
);

-- A published parameter set is immutable. Not "by convention" -- the
-- database refuses. Reproducing a 2025 determination in 2030 depends on
-- this holding (roadmap doc §3.5).
create or replace function policy_parameter_set_is_immutable() returns trigger
language plpgsql as $$
begin
    raise exception 'policy_parameter_set rows are immutable once published (attempted %)', tg_op;
end;
$$;

create trigger policy_parameter_set_no_mutation
    before update or delete on policy_parameter_set
    for each row execute function policy_parameter_set_is_immutable();

create trigger policy_parameter_no_mutation
    before update or delete on policy_parameter
    for each row execute function policy_parameter_set_is_immutable();

create index policy_parameter_lookup_idx on policy_parameter (parameter_set_id, name, household_size);
