"""Fraud Risk Triage's feature engineering (Phase 4 Task 2 plan, design doc
§2.2): reads a determination's household/income/verification history --
the same operational data the DMN engine itself read -- and shapes it into
the fixed numeric vector `score.py`'s `IsolationForest` scores. Read-only;
never writes anywhere.

Constraint 20 (Phase 4 plan) is enforced here, in code, not just stated in
a doc: `FEATURE_NAMES` is the complete, exhaustive set of columns that ever
reach the model, and `test_fraud_triage.py` asserts directly that none of
them is race, ethnicity, a national-origin signal, a standalone zip code, a
surname-derived signal, or a primary-language field.
"""

from __future__ import annotations

from uuid import UUID

import psycopg
from pydantic import BaseModel

from canopica_ai.config import Settings

# The exact four signals design doc §2.2 names. Order is significant --
# `FeatureVector.as_array()` and `score.py`'s fitted model both depend on
# this fixed order to line features up consistently across every case.
# Below this many income_record rows, there is nothing to compute a
# coefficient of variation against.
_MIN_RECORDS_FOR_VOLATILITY = 2

FEATURE_NAMES: tuple[str, ...] = (
    "income_volatility",
    "verification_discrepancy_rate",
    "household_composition_change_count",
    "benefit_amount_percentile_within_household_size_cohort",
)


class DeterminationNotFoundError(RuntimeError):
    """The message named a `determination_id` with no matching row. A
    determination commits and enqueues in the same transaction (design
    doc §2.2's outbox guarantee), so a miss here is a real bug worth
    surfacing through the normal retry/archive path, same reasoning
    `correspondence.service`'s own `DeterminationNotFoundError` gives."""


class FeatureVector(BaseModel):
    """One case's feature vector, named fields rather than a bare array so
    `top_contributing_features` (score.py) can report back *which* signal
    drove a score, not just its position in a list."""

    income_volatility: float
    verification_discrepancy_rate: float
    household_composition_change_count: float
    benefit_amount_percentile_within_household_size_cohort: float

    def as_array(self) -> list[float]:
        return [getattr(self, name) for name in FEATURE_NAMES]


def _resolve_household(determination_id: UUID, cur: psycopg.Cursor) -> tuple[UUID, UUID]:
    """Returns `(household_id, program_request_id)` -- everything else below
    joins off one of these two ids."""
    cur.execute(
        "select a.household_id, ed.program_request_id "
        "from eligibility_determination ed "
        "join program_request pr on pr.id = ed.program_request_id "
        "join application a on a.id = pr.application_id "
        "where ed.id = %s",
        (determination_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise DeterminationNotFoundError(f"determination {determination_id} not found")
    return row[0], row[1]


def _income_volatility(household_id: UUID, cur: psycopg.Cursor) -> float:
    """Coefficient of variation (population stdev / mean) of every income
    record ever reported for this household's members -- each effective-
    dated row is a resubmission, so a household whose reported income
    swings wildly across those rows volatilizes higher than one that
    reports the same figure every time. 0.0 for fewer than two records
    (nothing to vary against) or a zero mean (division is undefined, not
    infinitely volatile)."""
    cur.execute(
        "select stddev_pop(ir.monthly_amount), avg(ir.monthly_amount), count(*) "
        "from income_record ir "
        "join household_member hm on hm.person_id = ir.person_id "
        "where hm.household_id = %s",
        (household_id,),
    )
    row = cur.fetchone()
    assert row is not None  # aggregate query, always returns exactly one row
    stddev, mean, count = row
    if count is None or count < _MIN_RECORDS_FOR_VOLATILITY or not mean:
        return 0.0
    return float(stddev) / float(mean)


def _verification_discrepancy_rate(program_request_id: UUID, cur: psycopg.Cursor) -> float:
    """Fraction of this program request's verification responses that came
    back `DISCREPANCY` (V9's own outcome values: MATCHES/DISCREPANCY/
    UNAVAILABLE) -- 0.0 when there are no responses yet, not an undefined
    rate."""
    cur.execute(
        "select count(*) filter (where vr.outcome = 'DISCREPANCY'), count(vr.id) "
        "from verification v "
        "left join verification_response vr on vr.verification_id = v.id "
        "where v.program_request_id = %s",
        (program_request_id,),
    )
    row = cur.fetchone()
    assert row is not None  # aggregate query, always returns exactly one row
    discrepancies, total = row
    if not total:
        return 0.0
    return float(discrepancies) / float(total)


def _household_composition_change_count(household_id: UUID, cur: psycopg.Cursor) -> float:
    """Count of `household_member` rows whose `effective_from` is later
    than the household's own earliest -- each such row is a real
    composition change (a member added or re-added after the household's
    original formation), not the initial membership itself."""
    cur.execute(
        "select count(*) from household_member "
        "where household_id = %s and effective_from > "
        "(select min(effective_from) from household_member where household_id = %s)",
        (household_id, household_id),
    )
    row = cur.fetchone()
    assert row is not None  # aggregate query, always returns exactly one row
    (count,) = row
    return float(count)


def _benefit_amount_percentile(determination_id: UUID, cur: psycopg.Cursor) -> float:
    """This determination's `percent_rank()` among every determination's
    own `benefit_amount`, computed within the cohort of determinations
    that share the same household size as of their own `as_of_date` --
    household size is recomputed per determination the same way
    `FactAssembler.assemble` computes it in Java, not read off any
    person's current-day membership. 0.0 (the lowest possible rank, not a
    missing value) if this determination is alone in its own cohort --
    `percent_rank()` already returns 0 for a singleton partition."""
    cur.execute(
        """
        with sized as (
            select ed.id as determination_id, ed.benefit_amount,
                (select count(*) from household_member hm
                 where hm.household_id = a.household_id
                   and hm.effective_from <= ed.as_of_date
                   and (hm.effective_to is null
                        or hm.effective_to >= ed.as_of_date)) as household_size
            from eligibility_determination ed
            join program_request pr on pr.id = ed.program_request_id
            join application a on a.id = pr.application_id
        ),
        ranked as (
            select determination_id,
                   percent_rank() over (partition by household_size order by benefit_amount) as pct
            from sized
        )
        select pct from ranked where determination_id = %s
        """,
        (determination_id,),
    )
    row = cur.fetchone()
    return float(row[0]) if row is not None else 0.0


def fetch_feature_vector(determination_id: UUID, *, settings: Settings) -> FeatureVector:
    """The sole interface `score.py` needs to score one case."""
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        household_id, program_request_id = _resolve_household(determination_id, cur)
        return FeatureVector(
            income_volatility=_income_volatility(household_id, cur),
            verification_discrepancy_rate=_verification_discrepancy_rate(program_request_id, cur),
            household_composition_change_count=_household_composition_change_count(
                household_id, cur
            ),
            benefit_amount_percentile_within_household_size_cohort=_benefit_amount_percentile(
                determination_id, cur
            ),
        )


def fetch_population_feature_vectors(*, settings: Settings) -> dict[UUID, FeatureVector]:
    """Every determination's own feature vector, keyed by id -- the
    population `score.py` fits its `IsolationForest` against (design doc
    §2.11: batch fit against the available synthetic case population)."""
    with psycopg.connect(settings.operational_dsn) as conn, conn.cursor() as cur:
        cur.execute("select id from eligibility_determination")
        determination_ids = [row[0] for row in cur.fetchall()]
    return {
        determination_id: fetch_feature_vector(determination_id, settings=settings)
        for determination_id in determination_ids
    }
