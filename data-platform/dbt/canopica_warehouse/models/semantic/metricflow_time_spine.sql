{{ config(materialized='table') }}

-- MetricFlow requires a day-or-finer time spine somewhere in the project
-- before it will parse any semantic_models.yml -- found while running
-- `dbt parse` for the first time, not called out in the Task 4 plan.
-- Bounded on a rolling window around the current date (not a hardcoded
-- range) so it never goes stale and always covers real and seeded data.
with days as (
    {{
        dbt.date_spine(
            'day',
            "cast(current_date - interval '4 years' as date)",
            "cast(current_date + interval '30 days' as date)"
        )
    }}
)
select cast(date_day as date) as date_day
from days
