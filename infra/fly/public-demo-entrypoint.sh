#!/usr/bin/env bash
# Starts the three processes Task 9's public demo needs on one Fly.io
# machine: OpenSearch (retrieval), Ollama (embedding only -- generation
# is remote via OpenRouter regardless of this), and the FastAPI app.
#
# Not a production-grade supervisor: no signal forwarding to the
# backgrounded children, no restart-on-crash. Acceptable for a single-
# tenant demo container that serves read-only retrieval against a
# pre-indexed, image-baked corpus -- there is no in-flight write state to
# lose on an abrupt stop. Documented as a deliberate simplification, not
# an oversight.
set -euo pipefail

/usr/local/bin/ollama serve &

/usr/share/opensearch/opensearch-docker-entrypoint.sh &

echo "waiting for OpenSearch..."
for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:9200/_cluster/health >/dev/null 2>&1; then
    echo "OpenSearch is up."
    break
  fi
  sleep 2
done

cd /usr/share/opensearch/public-demo/ai

# Live-found gap (2026-08-31, first real Fly.io smoke test): the reranker
# model's *registration* survives into this image (baked in at build
# time, persisted as documents in .plugins-ml-model), but ml-commons
# "deployed" state is a live JVM in-memory allocation with no on-disk
# representation at all -- it cannot survive the build-time OpenSearch
# process being killed and a fresh one starting here. Without this call,
# the first real request fails with "Model not ready yet. Please deploy
# the model first." search_pipeline.py's setup() is already written to
# be idempotent ("safe to re-run against an already-configured
# cluster") -- it detects the model is already registered and only
# (re)deploys it, so this costs a few seconds on every boot rather than
# repeating the indexing work.
uv run --no-dev python -m canopica_ai.policy_intelligence.corpus.search_pipeline

exec uv run --no-dev --frozen uvicorn canopica_ai.public_demo.app:app --host 0.0.0.0 --port 8000
