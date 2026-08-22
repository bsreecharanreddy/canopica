{{ config(materialized='table') }}

-- SCD Type 2, sourced from data that is already effective-dated -- which is
-- why this dimension is trivial here and would not be if the operational
-- model stored only "current" (roadmap §3.5: policy_parameter_set rows are
-- immutable once published, enforced by a database trigger).
select
    id                                          as parameter_set_key,
    version_label,
    program_code,
    effective_from                              as valid_from,
    coalesce(effective_to, date '9999-12-31')   as valid_to,
    effective_to is null                        as is_current,
    source_citation
from {{ source('bronze', 'policy_parameter_set') }}
qualify row_number() over (partition by id order by _ingested_at desc) = 1
