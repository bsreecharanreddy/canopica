"""Fraud Risk Triage (Phase 4 Task 2 plan): the sole interface the
worker's `fraud_scoring_consumer.py` calls. Fetches the full case
population's feature vectors (`features.py`), fits and scores against them
(`score.py`), and returns a `FraudScore` -- never writes anywhere itself.
Same split `document_intake.service` and `correspondence.service` already
hold: this module scores, the worker is what actually persists anything.

No LLM anywhere in this path (design doc §2.2): a bounded numeric score
computed by a fitted `IsolationForest`, not free text a model generated.
"""

from __future__ import annotations

from uuid import UUID

from canopica_ai.config import Settings
from canopica_ai.fraud_triage.features import fetch_population_feature_vectors
from canopica_ai.fraud_triage.score import FraudScore, score_case


def score(determination_id: UUID, *, settings: Settings | None = None) -> FraudScore:
    settings = settings or Settings()
    population = fetch_population_feature_vectors(settings=settings)
    return score_case(determination_id, population)
