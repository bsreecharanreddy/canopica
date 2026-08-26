create table application (
    id                  uuid primary key,
    household_id        uuid        not null references household (id),
    submitted_at        timestamptz not null,
    channel             text        not null check (channel in ('ONLINE', 'PHONE', 'PAPER', 'IN_PERSON')),
    created_at          timestamptz not null default now()
);

-- PROGRAM_REQUEST is the unit of eligibility, not APPLICATION: one
-- application commonly requests several programs, each determined
-- separately, on its own timeline, with its own outcome (roadmap §3.4.1).
create table program_request (
    id                  uuid primary key,
    application_id      uuid        not null references application (id),
    program_code        text        not null check (program_code in ('SNAP')),
    status              text        not null check (status in
                            ('SUBMITTED', 'PENDING_VERIFICATION', 'DETERMINED', 'WITHDRAWN')),
    requested_on        date        not null,
    -- SNAP's federal processing standards: 30 days normal, 7 days expedited.
    -- Stored per request because expedited status is determined per request.
    is_expedited        boolean     not null default false,
    created_at          timestamptz not null default now(),
    constraint program_request_unique_per_application unique (application_id, program_code)
);

create table income_record (
    id                  uuid primary key,
    person_id           uuid        not null references person (id),
    income_type         text        not null check (income_type in
                            ('WAGES', 'SELF_EMPLOYMENT', 'UNEMPLOYMENT', 'SOCIAL_SECURITY',
                             'SSI', 'CHILD_SUPPORT', 'PENSION', 'OTHER_UNEARNED')),
    -- Whether this counts as earned income drives the 20% earned-income
    -- deduction, so it is stored, not inferred at evaluation time.
    is_earned           boolean     not null,
    monthly_amount      numeric(12, 2) not null check (monthly_amount >= 0),
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint income_record_effective_range check (effective_to is null or effective_to >= effective_from)
);

create table expense_record (
    id                  uuid primary key,
    person_id           uuid        not null references person (id),
    expense_type        text        not null check (expense_type in
                            ('RENT_OR_MORTGAGE', 'PROPERTY_TAX', 'HOME_INSURANCE', 'UTILITIES',
                             'DEPENDENT_CARE', 'MEDICAL', 'CHILD_SUPPORT_PAID')),
    monthly_amount      numeric(12, 2) not null check (monthly_amount >= 0),
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint expense_record_effective_range check (effective_to is null or effective_to >= effective_from)
);

create table living_arrangement (
    id                  uuid primary key,
    household_id        uuid        not null references household (id),
    arrangement_type    text        not null check (arrangement_type in
                            ('RENTS', 'OWNS', 'HOMELESS', 'SHARED_HOUSING', 'INSTITUTION')),
    pays_utilities_separately boolean not null default false,
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint living_arrangement_effective_range check (effective_to is null or effective_to >= effective_from)
);

create table work_activity (
    id                  uuid primary key,
    person_id           uuid        not null references person (id),
    activity_type       text        not null check (activity_type in
                            ('EMPLOYED', 'SEEKING_WORK', 'IN_TRAINING', 'STUDENT', 'NOT_WORKING')),
    weekly_hours        integer     not null default 0 check (weekly_hours >= 0),
    exemption_reason    text check (exemption_reason in
                            ('ELDERLY', 'DISABLED', 'CARETAKER', 'STUDENT', 'PREGNANT', 'NONE')),
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint work_activity_effective_range check (effective_to is null or effective_to >= effective_from)
);

create table disability_record (
    id                  uuid primary key,
    person_id           uuid        not null references person (id),
    -- "Disabled" for SNAP purposes is a specific definition tied to receipt
    -- of a qualifying benefit, not a self-reported status.
    basis               text        not null check (basis in
                            ('SSI', 'SSDI', 'VA_DISABILITY', 'STATE_DISABILITY', 'MEDICAID_DISABILITY')),
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint disability_record_effective_range check (effective_to is null or effective_to >= effective_from)
);

create table verification (
    id                  uuid primary key,
    program_request_id  uuid        not null references program_request (id),
    data_element        text        not null check (data_element in
                            ('IDENTITY', 'RESIDENCY', 'INCOME', 'SHELTER_COST', 'MEDICAL_EXPENSE',
                             'DISABILITY', 'HOUSEHOLD_COMPOSITION')),
    status              text        not null check (status in ('OUTSTANDING', 'RECEIVED', 'WAIVED')),
    due_on              date        not null,
    satisfied_on        date,
    created_at          timestamptz not null default now()
);

create table benefit_month (
    id                  uuid primary key,
    program_request_id  uuid        not null references program_request (id),
    -- Always the first of the month; benefits are computed per benefit month.
    benefit_month       date        not null,
    created_at          timestamptz not null default now(),
    constraint benefit_month_is_first_of_month check (extract(day from benefit_month) = 1),
    constraint benefit_month_unique unique (program_request_id, benefit_month)
);

create index income_record_person_idx on income_record (person_id, effective_from);
create index expense_record_person_idx on expense_record (person_id, effective_from);
create index program_request_application_idx on program_request (application_id);
create index verification_request_idx on verification (program_request_id, status);
