"""Unit tests for the hybrid-search pipeline's one-time cluster setup.

These drive `search_pipeline` through a fake at its single transport seam
rather than a live cluster: the two behaviours asserted here -- which
circuit-breaker thresholds get set, and whether an already-registered
reranker gets registered a *second* time -- are both invisible to the e2e
suite. The e2e suite runs against a container whose volume is created
fresh every time, so it can never observe the second run that the
idempotency bug actually breaks.
"""

from __future__ import annotations

from typing import Any

from canopica_ai.policy_intelligence.corpus import search_pipeline

_MODEL_GROUP_ID = "group-1"


def _model_hit(model_id: str, model_state: str) -> dict[str, Any]:
    return {
        "_id": model_id,
        "_source": {
            "name": search_pipeline.RERANKER_MODEL_NAME,
            "model_group_id": _MODEL_GROUP_ID,
            "model_state": model_state,
        },
    }


class _FakeOpenSearch:
    """Stands in for an OpenSearch client at `transport.perform_request`,
    the single seam `search_pipeline._request` goes through. Records every
    request so a test can assert on what was *not* sent."""

    def __init__(self, model_hits: list[dict[str, Any]] | None = None) -> None:
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []
        self._model_hits = model_hits or []
        self.transport = self

    def perform_request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.requests.append((method, path, body))
        return self._respond(path, body)

    def _respond(self, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        if path == "/_cluster/settings":
            return {"acknowledged": True}
        if path == "/_plugins/_ml/model_groups/_search":
            return {"hits": {"hits": [{"_id": _MODEL_GROUP_ID}]}}
        if path == "/_plugins/_ml/models/_search":
            return {"hits": {"hits": self._matching_models(body)}}
        if path == "/_plugins/_ml/models/_register":
            return {"task_id": "register-task"}
        if path.endswith("/_deploy"):
            return {"task_id": "deploy-task"}
        if path.startswith("/_plugins/_ml/tasks/"):
            return {"state": "COMPLETED", "model_id": "freshly-registered-model"}
        raise AssertionError(f"unexpected request to {path}")

    def _matching_models(self, body: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Applies the query's own `term` clauses rather than returning
        every staged model. Without this the fake would answer a
        `model_state: DEPLOYED` lookup with an undeployed model, and the
        test below would pass against the very code it exists to reject."""
        assert body is not None
        terms = [clause["term"] for clause in body["query"]["bool"]["must"]]
        return [
            hit
            for hit in self._model_hits
            if all(
                hit["_source"][field.removesuffix(".keyword")] == value
                for term in terms
                for field, value in term.items()
            )
        ]

    def paths(self) -> list[str]:
        return [path for _, path, _ in self.requests]


class TestMlCommonsSettings:
    def test_the_jvm_heap_breaker_is_raised_above_its_default(self) -> None:
        """ml-commons has two memory circuit breakers that emit the *same*
        "Memory Circuit Breaker is open" message. Only the host-memory one
        was ever raised here; the JVM-heap one sat at its 85% default,
        which is what a cross-encoder loaded into a 2g heap actually trips
        (measured 73% immediately after indexing, before query load)."""
        client = _FakeOpenSearch()

        search_pipeline.ensure_ml_commons_settings(client)  # type: ignore[arg-type]

        _, _, body = client.requests[0]
        assert body is not None
        threshold = body["persistent"]["plugins.ml_commons.jvm_heap_memory_threshold"]
        assert int(threshold) > 85


class TestReRankerModelIsRegisteredOnce:
    def test_a_reranker_marked_deployed_is_reused_not_re_registered_but_still_redeployed(
        self,
    ) -> None:
        """The real bug this test was added for (2026-08-31, first Fly.io
        smoke test): `model_state: DEPLOYED` is read from a document that
        is itself baked into the image at build time and persists across
        a fresh process start -- it reflects whatever the *previous*
        process left behind, not whether the *current* process has the
        model loaded in its own memory. A brand new process never does.
        Skipping `_deploy()` because the persisted field already says
        DEPLOYED left every fresh container's first real request failing
        with "Model not ready yet. Please deploy the model first." --
        `_deploy()` must be called every time regardless of this field;
        it's cheap and safe against a model already loaded in the current
        process (confirmed live: ~30ms versus ~40s for a real deploy)."""
        client = _FakeOpenSearch([_model_hit("deployed-model", "DEPLOYED")])

        model_id = search_pipeline.ensure_reranker_model(client, _MODEL_GROUP_ID)  # type: ignore[arg-type]

        assert model_id == "deployed-model"
        assert "/_plugins/_ml/models/_register" not in client.paths()
        assert "/_plugins/_ml/models/deployed-model/_deploy" in client.paths()

    def test_a_registered_but_undeployed_reranker_is_deployed_not_re_registered(self) -> None:
        """The real bug this file was written for: the lookup only matched
        `model_state: DEPLOYED`, so a model left REGISTERED by an
        interrupted deploy -- or DEPLOY_FAILED by a tripped memory circuit
        breaker, this stack's own most common failure -- was invisible, and
        the next run registered a second copy instead of redeploying it."""
        client = _FakeOpenSearch([_model_hit("registered-model", "REGISTERED")])

        model_id = search_pipeline.ensure_reranker_model(client, _MODEL_GROUP_ID)  # type: ignore[arg-type]

        assert model_id == "registered-model"
        assert "/_plugins/_ml/models/_register" not in client.paths()
        assert "/_plugins/_ml/models/registered-model/_deploy" in client.paths()

    def test_a_reranker_that_has_never_been_registered_is_registered_and_deployed(
        self,
    ) -> None:
        client = _FakeOpenSearch([])

        model_id = search_pipeline.ensure_reranker_model(client, _MODEL_GROUP_ID)  # type: ignore[arg-type]

        assert model_id == "freshly-registered-model"
        assert "/_plugins/_ml/models/_register" in client.paths()
        assert "/_plugins/_ml/models/freshly-registered-model/_deploy" in client.paths()
