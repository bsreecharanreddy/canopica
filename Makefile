# IES — one entry point per thing a developer or CI actually does.
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
	cd data-platform && uv run pytest -m "not e2e"

lint: ## Type-check and lint every language
	cd data-platform && uv run ruff check . && uv run mypy src tests
	cd portal/web && npm run typecheck

up: ## Bring up the full local stack
	docker compose -f infra/docker-compose.yml up -d --build

down: ## Tear the stack down, including volumes
	docker compose -f infra/docker-compose.yml down -v

e2e: ## Run the end-to-end slice test against a running stack
	cd data-platform && uv run pytest -m e2e

clean: ## Remove build output and the local warehouse
	./mvnw -B -q clean
	rm -rf portal/web/dist data-platform/warehouse
