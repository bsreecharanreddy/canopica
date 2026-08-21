"""Loads the committed ACS PUMS marginals and provides seeded-RNG sampling helpers over them.

Every sampling function here draws from marginal (independent) distributions, not a joint
one -- see ``docs/design/synthetic-data-methodology.md`` for what that does and doesn't let a
downstream fairness measurement claim.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

MARGINALS_PATH = Path(__file__).parent / "data" / "acs_pums_marginals.json"

# SNAP's own elderly threshold (FactAssembler.java: `asOf.minusYears(60)`) -- reusing it here,
# for both the marginals computed from PUMS and the generator sampling from them, ties the age
# bands to the same domain concept the rules engine evaluates against, not an arbitrary one.
_AGE_BANDS = [("0_17", 0, 17), ("18_59", 18, 59), ("60_plus", 60, None)]


def age_band(age: int) -> str:
    for name, low, high in _AGE_BANDS:
        if age >= low and (high is None or age <= high):
            return name
    raise ValueError(f"age {age} did not match any band")  # pragma: no cover -- AGEP/age is 0-99


@lru_cache(maxsize=1)
def load_marginals() -> dict[str, Any]:
    marginals: dict[str, Any] = json.loads(MARGINALS_PATH.read_text())
    return marginals


def weighted_choice(rng: np.random.Generator, weights: dict[str, float]) -> str:
    """Picks one key from a `{key: probability}` mapping, renormalized so it sums to 1."""
    keys = list(weights.keys())
    probabilities = np.array([weights[k] for k in keys], dtype=float)
    probabilities = probabilities / probabilities.sum()
    return str(rng.choice(keys, p=probabilities))


def sample_age(rng: np.random.Generator, age_histogram: dict[str, float]) -> int:
    """Picks a 5-year age bin by its observed share, then a uniform age within that bin."""
    bin_start = int(weighted_choice(rng, age_histogram))
    return bin_start + int(rng.integers(0, 5))


def sample_from_deciles(
    rng: np.random.Generator, deciles: list[float], floor: float = 0.0
) -> float:
    """
    Samples from 9 decile cutpoints (10th..90th percentile) by picking one of the 10 implied
    buckets uniformly, then a uniform value within that bucket. The top bucket's upper edge is
    estimated by extending the 80th-90th percentile gap past the 90th -- deciles alone don't
    say how long the tail actually is, so this is a documented approximation, not the true max.
    """
    top_bucket_width = deciles[-1] - deciles[-2]
    edges = [floor, *deciles, deciles[-1] + top_bucket_width]
    bucket = int(rng.integers(0, 10))
    return round(float(rng.uniform(edges[bucket], edges[bucket + 1])), 2)


def bernoulli(rng: np.random.Generator, probability: float) -> bool:
    return bool(rng.random() < probability)
