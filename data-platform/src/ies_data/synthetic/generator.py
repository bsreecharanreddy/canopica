"""Samples seeded, internally consistent synthetic households from the committed ACS PUMS
marginals. Every sampling call draws from the one `rng` instance the caller's seed governs, so
`generate_households(n, seed=s)` is exactly reproducible.

Deliberately marginal, not joint: household size, each member's age/role, disability,
employment, income, and shelter cost are each sampled from their own independent PUMS-derived
distribution, not from the true joint distribution actual households exhibit. Two structural
constraints are still enforced, cheaply, without a joint model: exactly one SELF per household,
and at most one SPOUSE/PARENT. See docs/design/synthetic-data-methodology.md for what this
does and doesn't let a downstream fairness measurement claim.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np

from ies_data.synthetic.distributions import (
    age_band,
    bernoulli,
    load_marginals,
    sample_age,
    sample_from_deciles,
    weighted_choice,
)
from ies_data.synthetic.models import (
    LivingArrangement,
    SyntheticExpense,
    SyntheticHousehold,
    SyntheticIncome,
    SyntheticPerson,
)

# A fixed anchor, not date.today(): reproducibility means the same seed produces the same
# output on any day, not just when called twice back to back in the same process.
REFERENCE_DATE = date(2026, 1, 1)

_COUNTIES = ["Ashcombe", "Brookhaven", "Cedarfield", "Deerpark", "Elmridge", "Fenwick"]
_CITIES = [
    "Fairview", "Riverside", "Cedar Grove", "Maple Falls", "Stonebridge", "Pinehurst", "Millbrook",
]
_STREET_NAMES = [
    "Main St", "Oak Ave", "Elm St", "Willow Way", "Sunset Blvd", "Highland Dr", "Birch Ln",
]
_FIRST_NAMES = {
    "M": [
        "James", "Michael", "Robert", "David", "Daniel",
        "Matthew", "Anthony", "Mark", "Kevin", "Brian",
    ],
    "F": [
        "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth",
        "Susan", "Jessica", "Karen", "Nancy", "Laura",
    ],
}
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones",
    "Garcia", "Miller", "Davis", "Martinez", "Wilson",
]

# ESR is N/A ("b") below this age in PUMS itself -- there is no real employment concept for a
# younger child, so the generator never samples earned income for one either.
_MIN_WORKING_AGE = 16


def _uuid_from_rng(rng: np.random.Generator) -> uuid.UUID:
    return uuid.UUID(bytes=rng.bytes(16))


def _date_of_birth(rng: np.random.Generator, age: int) -> date:
    month = int(rng.integers(1, 13))
    day = int(rng.integers(1, 29))  # capped at 28 -- avoids a Feb 29 that doesn't exist most years
    return date(REFERENCE_DATE.year - age, month, day)


def _pick_additional_relationship(
    rng: np.random.Generator, weights: dict[str, float], already_used_unique: set[str]
) -> str:
    available = {k: v for k, v in weights.items() if k not in already_used_unique}
    return weighted_choice(rng, available)


def _generate_member(
    rng: np.random.Generator, marginals: dict[str, Any], relationship: str
) -> SyntheticPerson:
    age = sample_age(rng, marginals["age_by_role"][relationship])
    sex = weighted_choice(rng, marginals["sex"])
    first_name = str(rng.choice(_FIRST_NAMES[sex]))
    last_name = str(rng.choice(_LAST_NAMES))
    return SyntheticPerson(
        person_id=_uuid_from_rng(rng),
        first_name=first_name,
        last_name=last_name,
        date_of_birth=_date_of_birth(rng, age),
        age=age,
        sex=sex,
        relationship=relationship,
    )


def _generate_income_for(
    rng: np.random.Generator, marginals: dict[str, Any], member: SyntheticPerson
) -> list[SyntheticIncome]:
    incomes: list[SyntheticIncome] = []

    if member.age >= _MIN_WORKING_AGE:
        employed = bernoulli(rng, marginals["employment_by_age_band"][age_band(member.age)])
        if employed:
            amount = sample_from_deciles(rng, marginals["earned_income_monthly_deciles"])
            incomes.append(
                SyntheticIncome(
                    person_id=member.person_id,
                    income_type="WAGES",
                    is_earned=True,
                    monthly_amount=Decimal(str(amount)),
                    effective_from=REFERENCE_DATE,
                )
            )

    if bernoulli(rng, marginals["p_has_unearned_income"]):
        amount = sample_from_deciles(rng, marginals["unearned_income_monthly_deciles"])
        incomes.append(
            SyntheticIncome(
                person_id=member.person_id,
                income_type="OTHER_UNEARNED",
                is_earned=False,
                monthly_amount=Decimal(str(amount)),
                effective_from=REFERENCE_DATE,
            )
        )

    return incomes


def _generate_shelter(
    rng: np.random.Generator, marginals: dict[str, Any], head: SyntheticPerson
) -> tuple[LivingArrangement, list[SyntheticExpense]]:
    arrangement_type = weighted_choice(rng, marginals["tenure"])
    expenses: list[SyntheticExpense] = []

    if arrangement_type == "RENTS":
        amount = sample_from_deciles(rng, marginals["rent_monthly_deciles"])
        expenses.append(_shelter_expense(head.person_id, amount))
    elif arrangement_type == "OWNS":
        amount = sample_from_deciles(rng, marginals["mortgage_monthly_deciles"])
        expenses.append(_shelter_expense(head.person_id, amount))
    # SHARED_HOUSING ("occupied without payment of rent" in PUMS) -- no shelter expense.

    pays_utilities_separately = bernoulli(rng, marginals["p_pays_utilities"])
    if pays_utilities_separately:
        amount = sample_from_deciles(rng, marginals["utility_monthly_deciles"])
        expenses.append(
            SyntheticExpense(
                person_id=head.person_id,
                expense_type="UTILITIES",
                monthly_amount=Decimal(str(amount)),
                effective_from=REFERENCE_DATE,
            )
        )

    living_arrangement = LivingArrangement(
        arrangement_type=arrangement_type, pays_utilities_separately=pays_utilities_separately
    )
    return living_arrangement, expenses


def _shelter_expense(person_id: uuid.UUID, amount: float) -> SyntheticExpense:
    return SyntheticExpense(
        person_id=person_id,
        expense_type="RENT_OR_MORTGAGE",
        monthly_amount=Decimal(str(amount)),
        effective_from=REFERENCE_DATE,
    )


def _generate_household(
    rng: np.random.Generator, marginals: dict[str, Any]
) -> SyntheticHousehold:
    size = int(weighted_choice(rng, marginals["household_size"]))

    head = _generate_member(rng, marginals, "SELF")
    members = [head]

    used_unique_relationships: set[str] = set()
    additional_relationship_weights = marginals["relationship_distribution_for_additional_members"]
    for _ in range(size - 1):
        relationship = _pick_additional_relationship(
            rng, additional_relationship_weights, used_unique_relationships
        )
        if relationship in ("SPOUSE", "PARENT"):
            used_unique_relationships.add(relationship)
        members.append(_generate_member(rng, marginals, relationship))

    incomes: list[SyntheticIncome] = []
    for member in members:
        incomes.extend(_generate_income_for(rng, marginals, member))

    living_arrangement, expenses = _generate_shelter(rng, marginals, head)

    # Wyoming's real ZIP range -- the same state the marginals themselves come from.
    zip_code = f"{int(rng.integers(82001, 83129)):05d}"

    return SyntheticHousehold(
        household_id=_uuid_from_rng(rng),
        county=f"{rng.choice(_COUNTIES)} County",
        address_line1=f"{int(rng.integers(100, 9999))} {rng.choice(_STREET_NAMES)}",
        city=str(rng.choice(_CITIES)),
        state="WY",
        zip_code=zip_code,
        members=members,
        incomes=incomes,
        expenses=expenses,
        living_arrangement=living_arrangement,
    )


def generate_households(count: int, *, seed: int) -> list[SyntheticHousehold]:
    rng = np.random.default_rng(seed)
    marginals = load_marginals()
    return [_generate_household(rng, marginals) for _ in range(count)]
