{{ config(materialized='table') }}

-- Disparate-impact ratio (EEOC's four-fifths rule shape: a slice's own favorable-outcome rate
-- divided by whichever slice has the HIGHEST rate, not an assumed majority reference group) per
-- (model, demographic_axis, demographic_slice, outcome_axis). This task (Phase 4 Task 1) builds
-- the rules_engine axis only, sliced by the applicant's own (SELF household_member) race and
-- hispanic_origin; Task 3 adds model = 'fraud_triage' once fraud_risk_score exists.
--
-- Grain is one refinement past the design doc's literal "(model, demographic_slice,
-- outcome_axis)" wording: race and hispanic_origin are different axes with different slice
-- vocabularies (7 categories vs. a boolean), so demographic_axis is a real 4th grain column, not
-- an oversight -- a Task-level detail the design doc's own §2.11 explicitly leaves open.
--
-- Aggregate only, by design (Phase 4 plan constraint 23): this mart never carries a
-- determination_key or person_key alongside a demographic value -- only a slice and its counts.

with applicant as (
    select
        hm.household_key,
        p.race,
        p.hispanic_origin
    from {{ ref('fct_household_member') }} hm
    inner join {{ ref('dim_person') }} p on p.person_key = hm.person_key
    where hm.relationship = 'SELF'
      and hm.effective_to is null
),

rules_engine_base as (
    select
        d.determination_key,
        d.eligible,
        a.race,
        a.hispanic_origin
    from {{ ref('fct_eligibility_determination') }} d
    inner join {{ ref('fct_program_request') }} r on r.program_request_key = d.program_request_key
    inner join {{ ref('fct_application') }} app on app.application_key = r.application_key
    inner join applicant a on a.household_key = app.household_key
),

race_slices as (
    select
        'rules_engine'                                  as model,
        'race'                                           as demographic_axis,
        race                                             as demographic_slice,
        'approval'                                       as outcome_axis,
        count(*)                                         as total_count,
        sum(case when eligible then 1 else 0 end)        as favorable_count
    from rules_engine_base
    where race is not null
    group by race
),

hispanic_origin_slices as (
    select
        'rules_engine'                                                        as model,
        'hispanic_origin'                                                     as demographic_axis,
        case when hispanic_origin then 'HISPANIC_OR_LATINO' else 'NOT_HISPANIC_OR_LATINO' end as demographic_slice,
        'approval'                                                            as outcome_axis,
        count(*)                                                              as total_count,
        sum(case when eligible then 1 else 0 end)                             as favorable_count
    from rules_engine_base
    where hispanic_origin is not null
    group by hispanic_origin
),

combined as (
    select * from race_slices
    union all
    select * from hispanic_origin_slices
),

rates as (
    select
        *,
        favorable_count::numeric / nullif(total_count, 0) as selection_rate,
        total_count >= 30 as sample_size_adequate
    from combined
),

reference as (
    -- Only an adequately-sized slice can anchor the reference rate -- a single-case slice's own
    -- selection_rate is 0.0 or 1.0 by construction, and letting that become the denominator every
    -- other slice's ratio is judged against would make the whole gate's output hostage to one
    -- case's luck. Real finding from testing this against a fixture with a genuine n=1 slice.
    select
        model,
        demographic_axis,
        outcome_axis,
        max(selection_rate) as reference_rate
    from rates
    where sample_size_adequate
    group by model, demographic_axis, outcome_axis
)

select
    -- Surrogate key: this mart's real grain is the 4-column combination below, not any single
    -- column, but the semantic layer (like every other model here) wants one primary-entity
    -- column to key off of. Plain md5/concat, not dbt_utils -- this project has no external dbt
    -- packages yet (packages.yml's own comment), and one string-concat hash doesn't need one.
    md5(concat_ws('|', rt.model, rt.demographic_axis, rt.demographic_slice, rt.outcome_axis)) as audit_row_key,
    -- No real event timestamp exists on an aggregate-of-aggregates row -- current_date is the
    -- run date, same "as of" reasoning mart_worker_caseload.sql's own as_of_date already uses.
    current_date as as_of_date,
    rt.model,
    rt.demographic_axis,
    rt.demographic_slice,
    rt.outcome_axis,
    rt.total_count,
    rt.favorable_count,
    rt.selection_rate,
    ref.reference_rate,
    -- The standard four-fifths-rule ratio. Below 0.8 is the conventional adverse-impact
    -- threshold, but a real finding from testing this mart against a realistic n=30 sample: a
    -- tiny slice's ratio swings wildly on pure sampling noise (n=1/n=2 slices produced 0.0 and
    -- 1.0 from nothing but chance in that run) -- exactly the "a threshold breached by a
    -- transient peak is a signal to handle, not a limit to raise" lesson this project already
    -- applies to CI flakiness elsewhere. sample_size_adequate is the handling: the CI gate (Task
    -- 1 Step 6, tests/gate_no_disparate_impact.sql) only fails on a row where this is true, not
    -- on every ratio below 0.8. Null (via the left join below) when no slice in this
    -- model/axis/outcome group is adequately sized yet to anchor a reference rate at all -- an
    -- honest "not enough data to say," not a fabricated ratio.
    round(rt.selection_rate / nullif(ref.reference_rate, 0), 4) as disparate_impact_ratio,
    -- 30 is a common minimum-N rule of thumb for a proportion comparison to mean anything (also
    -- EEOC's own guidance: the four-fifths rule is misleading on small samples) -- a stated
    -- default, not tuned against this project's own data, per design doc §2.11's own allowance
    -- for exactly this kind of Task-level number.
    rt.sample_size_adequate
from rates rt
left join reference ref
    on ref.model = rt.model
   and ref.demographic_axis = rt.demographic_axis
   and ref.outcome_axis = rt.outcome_axis
