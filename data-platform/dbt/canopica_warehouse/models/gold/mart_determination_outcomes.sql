{{ config(materialized='table') }}

select
    d.benefit_month,
    r.program_code,
    case when d.eligible then 'ELIGIBLE' else 'DENIED' end as outcome,
    d.reason_code,
    p.version_label                     as policy_parameter_version,
    count(*)                            as determination_count,
    count(*) filter (where d.eligible)  as eligible_count,
    sum(d.benefit_amount)               as total_benefit_amount,
    round(avg(d.benefit_amount), 2)     as average_benefit_amount
from {{ ref('fct_eligibility_determination') }} d
join {{ ref('fct_program_request') }} r on r.program_request_key = d.program_request_key
join {{ ref('dim_policy_parameter_set') }} p on p.parameter_set_key = d.parameter_set_key
group by 1, 2, 3, 4, 5
