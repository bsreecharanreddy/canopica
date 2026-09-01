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
opensearch_up=false
# Live-found gap (2026-09-01, first real stop/start cycle after the
# initial deploy): this loop's own budget used to be 60 x 2s = 120s
# with no check afterward -- if OpenSearch wasn't healthy by then, the
# script silently fell through anyway and the next step (below) crashed
# on a plain connection-refused, which killed the whole machine and,
# after Fly's own automatic restart-on-crash budget (10 attempts) was
# exhausted, left the demo permanently down with no clear error anywhere
# in the logs pointing at OpenSearch itself. Confirmed live via a real
# `flyctl logs --no-tail` capture: a genuine cold boot on this machine's
# shared-cpu tier had OpenSearch still mid-bootstrap (no "started"/
# cluster-formed line yet) more than 120s in, so 120s is not a reliably
# sufficient budget on real infrastructure, not just a number to
# increase for its own sake. Widened to 90 x 2s = 180s, and this loop
# now fails loudly (a clear "OpenSearch never became healthy" message
# and a nonzero exit) instead of silently proceeding into a confusing
# downstream crash if that's still not enough.
for _ in $(seq 1 90); do
  if curl -sf http://127.0.0.1:9200/_cluster/health >/dev/null 2>&1; then
    echo "OpenSearch is up."
    opensearch_up=true
    break
  fi
  sleep 2
done
if [ "$opensearch_up" != true ]; then
  echo "FATAL: OpenSearch never became healthy within 180s." >&2
  exit 1
fi

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
