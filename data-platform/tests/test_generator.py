from collections import Counter

import pytest

from canopica_data.synthetic.distributions import load_marginals
from canopica_data.synthetic.generator import generate_households


def test_generation_is_reproducible_for_a_given_seed() -> None:
    first = generate_households(50, seed=42)
    second = generate_households(50, seed=42)
    assert [h.model_dump_json() for h in first] == [h.model_dump_json() for h in second]


def test_different_seeds_produce_different_households() -> None:
    assert generate_households(50, seed=1) != generate_households(50, seed=2)


def test_household_size_distribution_matches_the_pums_marginal() -> None:
    households = generate_households(5_000, seed=7)
    observed = Counter(len(h.members) for h in households)
    expected = load_marginals()["household_size"]
    for size, share in expected.items():
        assert observed[int(size)] / 5_000 == pytest.approx(share, abs=0.02)


def test_every_household_is_internally_consistent() -> None:
    for household in generate_households(500, seed=3):
        assert len(household.members) >= 1
        assert sum(m.relationship == "SELF" for m in household.members) == 1
        assert all(i.monthly_amount >= 0 for i in household.incomes)
        # Income belongs to a member of this household, not a stranger.
        member_ids = {m.person_id for m in household.members}
        assert all(i.person_id in member_ids for i in household.incomes)
        # Only working-age members have earned income.
        earners = {i.person_id for i in household.incomes if i.is_earned}
        ages = {m.person_id: m.age for m in household.members}
        assert all(ages[p] >= 16 for p in earners)
        # At most one SPOUSE and at most one PARENT per household (a cheap, deliberate
        # constraint on top of otherwise-independent marginal sampling -- see generator.py).
        relationships = [m.relationship for m in household.members]
        assert relationships.count("SPOUSE") <= 1
        assert relationships.count("PARENT") <= 1


def test_generated_payload_validates_against_the_real_intake_contract() -> None:
    # The generator's output must match Task 7's actual, deployed IntakeRequest shape -- not
    # just look plausible -- since a drift here is exactly what would break Task 13's e2e test.
    # IntakePersonDto nests incomes/expenses per member and there is no top-level
    # "livingArrangement" object; arrangementType/paysUtilitiesSeparately are flat fields on
    # IntakeRequest itself (api/src/main/java/canopica/api/api/dto/IntakeRequest.java).
    payload = generate_households(1, seed=11)[0].to_intake_payload()
    assert set(payload) == {
        "county", "addressLine1", "city", "state", "zipCode",
        "arrangementType", "paysUtilitiesSeparately", "members",
    }
    members = payload["members"]
    assert isinstance(members, list)
    member = members[0]
    assert set(member) >= {
        "firstName", "lastName", "dateOfBirth", "sex", "relationship", "incomes", "expenses",
    }
