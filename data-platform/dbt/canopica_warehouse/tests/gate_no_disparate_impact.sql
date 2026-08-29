-- The fairness CI gate (roadmap §3.3, Phase 4 design doc §2.1): fails this dbt run/build if any
-- adequately-sampled demographic slice's disparate-impact ratio drops below the standard
-- four-fifths threshold, for either model this mart covers. A dbt singular test, not a Python
-- step -- it runs automatically as part of the same `dbt build` this project's CI job already
-- runs, "a gate that runs in CI and blocks a merge on regression, not just gets described in a
-- doc" without needing separate wiring. sample_size_adequate (mart_fairness_audit.sql's own
-- comment) is why this doesn't just check `disparate_impact_ratio < 0.8` directly -- a small
-- slice's ratio is sampling noise, not a signal, and a gate that can't tell the difference isn't
-- a gate worth having (data-platform/tests/test_fairness_gate.py proves this test actually fires
-- on a real induced disparity, using conftest.py's seeded_fairness_dsn fixture).
select *
from {{ ref('mart_fairness_audit') }}
where sample_size_adequate
  and disparate_impact_ratio < 0.8
