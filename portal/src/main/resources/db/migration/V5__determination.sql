create table eligibility_determination (
    id                      uuid primary key,
    program_request_id      uuid        not null references program_request (id),
    benefit_month           date        not null,
    -- The date the facts and parameters were resolved as of. Not the same as
    -- decided_at: a determination can be made today for a past benefit month.
    as_of_date              date        not null,
    eligible                boolean     not null,
    benefit_amount          numeric(12, 2) not null check (benefit_amount >= 0),
    reason_code             text        not null check (reason_code in
                                ('ELIGIBLE', 'GROSS_INCOME_EXCEEDS_LIMIT',
                                 'NET_INCOME_EXCEEDS_LIMIT', 'ZERO_BENEFIT_AMOUNT')),
    -- The version used, stored as a value, not a pointer to "current".
    policy_parameter_set_id uuid        not null references policy_parameter_set (id),
    policy_parameter_version text       not null,
    decided_at              timestamptz not null default now(),
    decided_by              text        not null,
    constraint eligibility_determination_benefit_month_first check (extract(day from benefit_month) = 1),
    constraint eligibility_determination_eligible_has_benefit
        check ((eligible and benefit_amount > 0) or (not eligible and benefit_amount = 0))
);

create table determination_trace (
    id                      uuid primary key,
    determination_id        uuid        not null unique references eligibility_determination (id),
    -- The exact facts fed to the engine, as of as_of_date.
    input_snapshot          jsonb       not null,
    -- Every named DMN decision's result, in evaluation order.
    decision_results        jsonb       not null,
    dmn_model_name          text        not null,
    -- SHA-256 of the .dmn file the evaluation ran against, so a later
    -- re-derivation can prove it used the same model, not just the same numbers.
    dmn_model_hash          text        not null,
    engine_version          text        not null,
    created_at              timestamptz not null default now()
);

-- Append-only: a changed circumstance produces a NEW determination
-- (roadmap doc §3.4.1). The database refuses anything else.
create or replace function determination_is_append_only() returns trigger
language plpgsql as $$
begin
    raise exception 'eligibility_determination is append-only (attempted %); '
                    'record a new determination instead', tg_op;
end;
$$;

create trigger eligibility_determination_no_mutation
    before update or delete on eligibility_determination
    for each row execute function determination_is_append_only();

create trigger determination_trace_no_mutation
    before update or delete on determination_trace
    for each row execute function determination_is_append_only();

create index eligibility_determination_request_idx
    on eligibility_determination (program_request_id, benefit_month, decided_at desc);
