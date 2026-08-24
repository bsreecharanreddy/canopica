{{ config(materialized='table') }}

-- SCD Type 2, sourced from data that is already effective-dated -- which is
-- why this dimension is trivial here and would not be if the operational
-- model stored only "current" (roadmap §3.5: policy_parameter_set rows are
-- immutable once published, enforced by a database trigger).
--
-- One exception, and the `qualify` below is what absorbs it: V15 narrowed
-- that trigger to permit closing an open-ended range (effective_to null -> a
-- date) when a superseding set is published, so a set can legitimately land
-- in bronze twice with a different effective_to. Taking the latest ingest per
-- id is already the correct reading of that -- the close is the newer truth,
-- not a second version of the set. See
-- docs/design/2026-08-23-policy-parameter-supersession.md.
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
