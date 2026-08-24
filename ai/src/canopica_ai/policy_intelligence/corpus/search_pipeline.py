"""One-time setup for the CFR corpus's hybrid search pipeline: ml-commons
cluster settings, the reranker model group/model, and the RRF-fusion +
cross-encoder-rerank search pipeline itself (infra/opensearch/
search_pipeline.json). Idempotent -- every step checks before creating, so
re-running this against an already-configured cluster is a no-op, not a
duplicate.

**A real correction from this plan's own assumption, found here**: the
implementation plan describes RRF as configured via a
"normalization-processor with technique: rrf". As of OpenSearch 2.19 (the
version this repo pins, chosen specifically *for* RRF support) that isn't
how RRF is exposed -- ``normalization-processor`` supports only
``min_max``/``l2``/``arithmetic_mean``-style combination; RRF is its own,
separate ``score-ranker-processor`` (a ``phase_results_processors`` stage,
not a ``response_processors`` one), verified against OpenSearch's current
documentation before writing search_pipeline.json below.

    uv run python -m canopica_ai.policy_intelligence.corpus.search_pipeline
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch

from canopica_ai.config import Settings

# ai/src/canopica_ai/policy_intelligence/corpus/search_pipeline.py -> repo root -> infra/opensearch
PIPELINE_CONFIG_PATH = (
    Path(__file__).resolve().parents[5] / "infra" / "opensearch" / "search_pipeline.json"
)

MODEL_GROUP_NAME = "cfr-rerank-models"
# Pinned at implementation time: an ONNX-exported, OpenSearch-hosted
# pretrained cross-encoder (design doc §2.1's "small cross-encoder, e.g. an
# ONNX-exported ms-marco-MiniLM-family model"), registered from
# OpenSearch's own pretrained-model repository, not a custom upload.
RERANKER_MODEL_NAME = "huggingface/cross-encoders/ms-marco-MiniLM-L-6-v2"
RERANKER_MODEL_VERSION = "1.0.2"
RERANKER_MODEL_FORMAT = "ONNX"

_POLL_INTERVAL_SECONDS = 3.0
_POLL_TIMEOUT_SECONDS = 120.0


def _request(client: OpenSearch, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    return client.transport.perform_request(method, path, body=body)


def ensure_ml_commons_settings(client: OpenSearch) -> None:
    """Required for ml-commons to run a *local* (non-remote) model on a
    single-node cluster with no dedicated ML node -- without these, model
    deployment fails outright (a real "Memory Circuit Breaker is open"
    failure was hit during implementation before OpenSearch's own heap was
    also raised in infra/docker-compose.yml; these settings are the other
    half of that fix)."""
    _request(
        client,
        "PUT",
        "/_cluster/settings",
        {
            "persistent": {
                "plugins.ml_commons.allow_registering_model_via_url": "true",
                "plugins.ml_commons.only_run_on_ml_node": "false",
                "plugins.ml_commons.model_access_control_enabled": "true",
                "plugins.ml_commons.native_memory_threshold": "99",
                # ml-commons has *two* memory circuit breakers and both emit
                # the byte-for-byte identical "Memory Circuit Breaker is
                # open" message, which is why this took several rounds to
                # find: `native_memory_threshold` above measures host RAM,
                # and `jvm_heap_memory_threshold` here measures JVM heap.
                # Only the first was ever raised, so every earlier fix
                # attempt (freeing host services, quantizing Ollama's KV
                # cache, splitting the e2e jobs) targeted a resource that
                # was not the binding one -- with host memory at 92% against
                # a 99% threshold, that breaker was never the one tripping.
                # Measured on this stack's own container: with the
                # cross-encoder reranker deployed into the 2g heap, heap sits
                # at 73% immediately after indexing and before any query
                # load, one allocation burst from the 85% default. 92 keeps a
                # real margin and still sits below OpenSearch's own parent
                # breaker (`indices.breaker.total.limit`, 95% of heap), which
                # remains the backstop against actually exhausting the JVM.
                "plugins.ml_commons.jvm_heap_memory_threshold": "92",
            }
        },
    )


def _poll_task(client: OpenSearch, task_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        task = _request(client, "GET", f"/_plugins/_ml/tasks/{task_id}")
        if task["state"] == "COMPLETED":
            return dict(task)
        if task["state"] == "FAILED":
            raise RuntimeError(f"ml-commons task {task_id} failed: {task.get('error')}")
        time.sleep(_POLL_INTERVAL_SECONDS)
    raise TimeoutError(
        f"ml-commons task {task_id} did not complete within {_POLL_TIMEOUT_SECONDS}s"
    )


def ensure_model_group(client: OpenSearch) -> str:
    """Returns the existing model group's id if one by this name already
    exists, else registers a new one."""
    search_response = _request(
        client,
        "POST",
        "/_plugins/_ml/model_groups/_search",
        {"query": {"term": {"name.keyword": MODEL_GROUP_NAME}}},
    )
    hits = search_response.get("hits", {}).get("hits", [])
    if hits:
        return str(hits[0]["_id"])

    register_response = _request(
        client,
        "POST",
        "/_plugins/_ml/model_groups/_register",
        {
            "name": MODEL_GROUP_NAME,
            "description": "Local cross-encoder models for CFR corpus reranking",
        },
    )
    return str(register_response["model_group_id"])


def ensure_reranker_model(client: OpenSearch, model_group_id: str) -> str:
    """Returns the pinned cross-encoder's model_id, registering it first if
    this group has no copy of it yet and deploying it if the copy it has
    isn't loaded.

    Registration and deployment are deliberately two separate decisions.
    An earlier version asked one question -- "is there a DEPLOYED copy?" --
    and registered a fresh one whenever the answer was no, which makes a
    model left behind in any other state invisible rather than reusable.
    DEPLOY_FAILED is exactly what a tripped memory circuit breaker leaves
    behind, so that path is directly reachable from this stack's own most
    common failure: the run after a breaker trip would register a second
    copy of a ~90MB model rather than redeploying the one already there,
    adding heap pressure to a cluster that just ran out of it. CI cannot
    catch this -- its OpenSearch volume is created fresh every run, so
    there is never a second run to be wrong about."""
    search_response = _request(
        client,
        "POST",
        "/_plugins/_ml/models/_search",
        {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"name.keyword": RERANKER_MODEL_NAME}},
                        {"term": {"model_group_id": model_group_id}},
                    ]
                }
            }
        },
    )
    hits = search_response.get("hits", {}).get("hits", [])
    if hits:
        model_id = str(hits[0]["_id"])
        if hits[0].get("_source", {}).get("model_state") == "DEPLOYED":
            return model_id
        return _deploy(client, model_id)

    register_task = _request(
        client,
        "POST",
        "/_plugins/_ml/models/_register",
        {
            "name": RERANKER_MODEL_NAME,
            "version": RERANKER_MODEL_VERSION,
            "model_group_id": model_group_id,
            "model_format": RERANKER_MODEL_FORMAT,
        },
    )
    registered = _poll_task(client, register_task["task_id"])
    return _deploy(client, str(registered["model_id"]))


def _deploy(client: OpenSearch, model_id: str) -> str:
    deploy_task = _request(client, "POST", f"/_plugins/_ml/models/{model_id}/_deploy")
    _poll_task(client, deploy_task["task_id"])
    return model_id


def ensure_search_pipeline(client: OpenSearch, settings: Settings, model_id: str) -> None:
    """(Re)creates the named search pipeline pointing at model_id. A PUT
    on a search pipeline is itself an idempotent upsert, so this always
    just runs -- the reranker model_id is the only value that can
    meaningfully change between runs."""
    config = json.loads(PIPELINE_CONFIG_PATH.read_text(encoding="utf-8"))
    config["response_processors"][0]["rerank"]["ml_opensearch"]["model_id"] = model_id
    _request(client, "PUT", f"/_search/pipeline/{settings.cfr_search_pipeline}", config)


def setup(client: OpenSearch, settings: Settings) -> str:
    """Runs every step above in order; returns the deployed reranker's
    model_id. Safe to re-run against an already-configured cluster."""
    ensure_ml_commons_settings(client)
    model_group_id = ensure_model_group(client)
    model_id = ensure_reranker_model(client, model_group_id)
    ensure_search_pipeline(client, settings, model_id)
    return model_id


def main() -> None:
    settings = Settings()
    client = OpenSearch(hosts=[settings.opensearch_url])
    model_id = setup(client, settings)
    print(
        f"search pipeline {settings.cfr_search_pipeline!r} ready (reranker model_id={model_id})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
