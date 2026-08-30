-- Phase 4 Task 9's own deterministic data-quality fixture (design doc
-- §2.7: "when a dbt test fails... gather structured failure context...
-- and draft a plain-language root-cause summary"). A determination
-- decided before its own application was even submitted is a genuine
-- data-integrity violation, not a synthetic trigger flag -- real
-- pipeline data can't produce this shape (Task 6's own application ->
-- program_request -> determination flow always submits first), so this
-- only ever fires against test_data_quality.py's own dedicated seeded
-- fixture, the same "only a dedicated fixture makes this fire" property
-- gate_no_disparate_impact.sql already establishes for a different axis.
select *
from {{ ref('mart_processing_timeliness') }}
where processing_days < 0
