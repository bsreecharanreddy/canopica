-- Household-level: liquid resources (bank accounts, cash) are countable per
-- case, not per member, unlike income/expense which are per person. Feeds
-- expedited (7-day) SNAP processing eligibility (7 CFR 273.2(i)) -- the
-- data gap that left program_request.is_expedited unset since Phase 1a.
create table resource_record (
    id                  uuid primary key,
    household_id        uuid        not null references household (id),
    resource_type       text        not null check (resource_type in ('CASH', 'BANK_ACCOUNT', 'OTHER_LIQUID')),
    amount              numeric(12, 2) not null check (amount >= 0),
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint resource_record_effective_range check (effective_to is null or effective_to >= effective_from)
);
create index resource_record_household_idx on resource_record (household_id, effective_from);
