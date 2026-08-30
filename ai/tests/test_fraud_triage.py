"""Fraud Risk Triage's feature engineering and scoring (Phase 4 Task 2
plan, design doc §2.2). Plain unit tests against hand-built `FeatureVector`
fixtures -- no live Postgres required, matching `score_case`'s own
interface, which takes feature vectors, not a database connection.
`features.py`'s real Postgres queries have their own coverage via
`worker/tests/test_fraud_scoring_consumer.py`'s end-to-end integration
test, per the Phase 4 plan's own split of responsibility.
"""

from __future__ import annotations

import uuid

from canopica_ai.fraud_triage.features import FEATURE_NAMES, FeatureVector
from canopica_ai.fraud_triage.score import score_case

# Constraint 20 (Phase 4 plan): the fraud-risk model's feature set must
# never include race, ethnicity, national origin, or their documented
# statistical proxies (zip code as a standalone feature, surname-derived
# signals, primary language).
_EXCLUDED_SIGNALS = (
    "race",
    "hispanic",
    "ethnic",
    "national_origin",
    "zip",
    "surname",
    "last_name",
    "language",
)


class TestFeatureSetExcludesProtectedSignals:
    def test_feature_names_never_include_an_excluded_signal(self) -> None:
        for name in FEATURE_NAMES:
            for excluded in _EXCLUDED_SIGNALS:
                assert excluded not in name.lower(), (
                    f"feature {name!r} looks like it encodes the excluded signal {excluded!r}"
                )


def _typical_vector(income_volatility: float = 0.05) -> FeatureVector:
    return FeatureVector(
        income_volatility=income_volatility,
        verification_discrepancy_rate=0.0,
        household_composition_change_count=1.0,
        benefit_amount_percentile_within_household_size_cohort=0.5,
    )


class TestScoreCase:
    def test_a_deliberately_anomalous_case_scores_higher_than_typical_cases(self) -> None:
        typical_ids = [uuid.uuid4() for _ in range(19)]
        anomalous_id = uuid.uuid4()

        population = {tid: _typical_vector(income_volatility=0.03 + i * 0.005)
                      for i, tid in enumerate(typical_ids)}
        # Income reported three wildly different ways across resubmissions,
        # every verification response a discrepancy, the household's
        # composition changing constantly -- exactly the plan's own worked
        # example of an anomalous case.
        population[anomalous_id] = FeatureVector(
            income_volatility=4.5,
            verification_discrepancy_rate=1.0,
            household_composition_change_count=12.0,
            benefit_amount_percentile_within_household_size_cohort=0.98,
        )

        anomalous_result = score_case(anomalous_id, population)
        typical_results = [score_case(tid, population) for tid in typical_ids]

        assert anomalous_result.score > max(r.score for r in typical_results)
        assert 0.0 <= anomalous_result.score <= 1.0

    def test_top_contributing_features_are_named_from_the_real_feature_set(self) -> None:
        typical_ids = [uuid.uuid4() for _ in range(9)]
        anomalous_id = uuid.uuid4()
        population = {tid: _typical_vector() for tid in typical_ids}
        population[anomalous_id] = FeatureVector(
            income_volatility=5.0,
            verification_discrepancy_rate=0.0,
            household_composition_change_count=1.0,
            benefit_amount_percentile_within_household_size_cohort=0.5,
        )

        result = score_case(anomalous_id, population)

        assert len(result.top_contributing_features) <= 3
        assert all(c.feature in FEATURE_NAMES for c in result.top_contributing_features)
        # income_volatility is the one deliberately extreme feature here --
        # it should dominate the ranking.
        assert result.top_contributing_features[0].feature == "income_volatility"

    def test_a_degenerate_single_case_population_scores_zero_not_arbitrary(self) -> None:
        only_id = uuid.uuid4()
        result = score_case(only_id, {only_id: _typical_vector()})
        assert result.score == 0.0
