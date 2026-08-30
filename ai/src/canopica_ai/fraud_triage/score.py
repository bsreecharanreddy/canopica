"""Fraud Risk Triage's `IsolationForest` wrapper (Phase 4 Task 2 plan,
design doc §2.2/§2.11): fits fresh against the available synthetic case
population on every call -- deliberately not a persisted/scheduled model
artifact. At this project's real synthetic-population scale (dozens to a
few hundred determinations) refitting per score is cheap and always
current; a real deployment at genuine production scale would move to the
batch-fit-on-a-schedule shape design doc §2.11 describes, which is the one
real cost this substitution carries (recorded in the tradeoffs doc's own
Fraud risk triage row).

Per-feature "top contributing" attribution is a z-score against the same
fitted population's own mean/stdev per feature, not isolation-path-length
decomposition (`sklearn.ensemble.IsolationForest` exposes no public path-
length-per-feature API) -- comparably explainable, and simple enough to
test deterministically against a fixture population.
"""

from __future__ import annotations

from uuid import UUID

import numpy as np
from pydantic import BaseModel, Field
from sklearn.ensemble import IsolationForest

from canopica_ai.fraud_triage.features import FEATURE_NAMES, FeatureVector

MODEL_VERSION = "isolation-forest-v1"

# How many of the four features to report per score -- deliberately not
# all four: `top_contributing_features` is meant to draw a reviewer's eye
# to what's unusual about this case, and every feature always being listed
# would defeat that (Task 3's own review-queue UI, design doc §2.12's
# "structured display, not free text").
_TOP_N_FEATURES = 3

# A random but fixed seed keeps a given (case, population) pair's score
# reproducible across repeated runs -- same reasoning this project's DMN
# evaluator holds to for a binding decision (roadmap §3.5), applied here
# to an advisory one for the same "explainable, not different every time
# you look" reason.
_RANDOM_STATE = 42


class FeatureContribution(BaseModel):
    feature: str
    value: float
    z_score: float


class FraudScore(BaseModel):
    """`score()`'s sole return type -- the worker consumer's only interface
    into this module, per the Phase 4 plan's own Interfaces note."""

    score: float = Field(ge=0, le=1)
    top_contributing_features: list[FeatureContribution]
    model_version: str = MODEL_VERSION


def _matrix(vectors: list[FeatureVector]) -> np.ndarray:
    return np.array([vector.as_array() for vector in vectors], dtype=float)


def score_case(
    target_id: UUID, population: dict[UUID, FeatureVector]
) -> FraudScore:
    """`population` must include `target_id` -- the case being scored is
    itself part of the population its own anomaly score is measured
    against, same as every other case."""
    if target_id not in population:
        raise KeyError(f"target_id {target_id} not present in population")

    ids = list(population.keys())
    matrix = _matrix([population[i] for i in ids])
    target_index = ids.index(target_id)

    model = IsolationForest(random_state=_RANDOM_STATE)
    model.fit(matrix)

    # score_samples: higher = more normal. Negated so higher = more
    # anomalous, then min-max normalized across this same population so
    # the result is a bounded, comparable [0, 1] figure rather than
    # IsolationForest's own unbounded raw score.
    anomaly_raw = -model.score_samples(matrix)
    low, high = anomaly_raw.min(), anomaly_raw.max()
    # `high == low` is a degenerate, e.g. single-case, population -- nothing
    # to distinguish "anomalous" from "typical" yet, so no case is flagged
    # rather than an arbitrary midpoint.
    normalized = (
        (anomaly_raw - low) / (high - low) if high > low else np.zeros_like(anomaly_raw)
    )

    target_score = float(normalized[target_index])

    mean = matrix.mean(axis=0)
    stdev = matrix.std(axis=0)
    target_row = matrix[target_index]
    z_scores = np.divide(
        target_row - mean, stdev, out=np.zeros_like(target_row), where=stdev != 0
    )

    contributions = sorted(
        (
            FeatureContribution(feature=name, value=float(value), z_score=float(z))
            for name, value, z in zip(FEATURE_NAMES, target_row, z_scores, strict=True)
        ),
        key=lambda c: abs(c.z_score),
        reverse=True,
    )[:_TOP_N_FEATURES]

    return FraudScore(
        score=target_score, top_contributing_features=contributions, model_version=MODEL_VERSION
    )
