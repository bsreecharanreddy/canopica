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
exec uv run --no-dev --frozen uvicorn canopica_ai.public_demo.app:app --host 0.0.0.0 --port 8000
