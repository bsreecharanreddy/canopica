# Canopica — one entry point per thing a developer or CI actually does.
# Every target here is also what the CI workflow runs, so "green locally"
# and "green in CI" cannot drift apart.

.PHONY: help build test lint up down seed pipeline e2e clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

build: ## Compile the Java modules and build the web bundle
	./mvnw -B -q verify -DskipTests
	cd portal/web && npm ci && npm run build

test: ## Run every unit/integration suite that does not need the Compose stack
	./mvnw -B verify
	cd portal/web && npm test
	# TESTCONTAINERS_RYUK_DISABLED works around a Docker-Desktop-for-macOS-
	# specific bug in testcontainers-python's Ryuk reaper container ("error
	# while creating mount source path ...docker.sock: operation not
	# supported") -- not needed in CI (Linux runners), and does not affect
	# the Java Testcontainers tests above, which hit ./mvnw's own JVM-side
	# Testcontainers, unaffected by this.
	cd data-platform && TESTCONTAINERS_RYUK_DISABLED=true uv run pytest -m "not e2e"

lint: ## Type-check and lint every language
	cd data-platform && uv run ruff check . && uv run mypy src tests
	cd portal/web && npm run typecheck && npm run lint

up: ## Bring up the full local stack
	docker compose -f infra/docker-compose.yml up -d --build

down: ## Tear the stack down, including volumes
	docker compose -f infra/docker-compose.yml down -v

seed: ## Generate + load 500 synthetic households into the running stack
	cd data-platform && uv run python -m canopica_data.synthetic.cli generate --count 500 --seed 42 --out /tmp/canopica-households.jsonl
	cd data-platform && uv run python -m canopica_data.synthetic.cli load --input /tmp/canopica-households.jsonl --api http://localhost:8080

pipeline: ## Ingest -> dbt build -> serving materialization -> Metabase provisioning
	docker compose -f infra/docker-compose.yml --profile pipeline run --rm pipeline

e2e: ## Run the end-to-end slice test against a running stack
	cd data-platform && uv run pytest -m e2e

clean: ## Remove build output and the local warehouse
	./mvnw -B -q clean
	rm -rf portal/web/dist data-platform/warehouse
