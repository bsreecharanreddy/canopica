-- Voluntary civil-rights demographic data (7 CFR 272.6), not an eligibility input -- the DMN
-- rules engine never reads either column. Nullable: a real applicant may decline to answer.
-- Exists so Phase 4's fairness audit (mart_fairness_audit) has a real demographic axis to slice
-- determinations by; see the Phase 4 design doc §2.1/§2.2 and roadmap §3.3's no-proxy-features
-- row this data exists to check, not to feed into any model. race's check constraint mirrors OMB
-- Statistical Policy Directive 15's categories (see data-platform's fetch_pums.py _RACE_MAP for
-- the ACS PUMS RAC1P mapping that produces these same values in synthetic data).
alter table person
    add column race text check (race is null or race in (
        'WHITE', 'BLACK_OR_AFRICAN_AMERICAN', 'AMERICAN_INDIAN_OR_ALASKA_NATIVE',
        'ASIAN', 'NATIVE_HAWAIIAN_OR_PACIFIC_ISLANDER', 'SOME_OTHER_RACE', 'TWO_OR_MORE_RACES'
    )),
    add column hispanic_origin boolean;
