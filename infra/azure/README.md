# Reference Terraform for Azure

Reference only. `terraform validate` and `terraform fmt -check` run in CI
(the `terraform` job); nothing here is ever applied against a live
subscription, and there is no state backend configured — that's a
deliberate absence, not an oversight (see below).

## What's modeled

Matched one-for-one against `infra/docker-compose.yml`'s own services:

| This repo (local, `docker compose`) | This config (`infra/azure/`) |
|---|---|
| `postgres` (`canopica_operational`, `canopica_serving`, `airflow` databases) | Azure Database for PostgreSQL Flexible Server, three databases on one server |
| `portal-api`, `portal-web` | Azure Container Apps |
| `airflow-webserver`, `airflow-scheduler` | Azure Container Apps (`args = ["webserver"]` / `["scheduler"]`, same as Compose's own `command:` override) |
| `.env` / Compose environment variables | Azure Key Vault (holds the generated Postgres admin password) + Container App secrets |
| — | Log Analytics Workspace + a diagnostic setting on the Postgres server — the Observability row's real-production target per the tradeoffs doc |
| — | Azure Container Registry — `portal_api_image` / `portal_web_image` / `airflow_image` are expected to already be pushed there |

## What's deliberately absent

Stated plainly rather than left for a reader to discover, same standard
the README's own "Honest limitations" section holds the rest of the repo
to:

- **Keycloak, Metabase, and the Jaeger/Prometheus/Grafana stack.** Not in
  this task's own resource list (`docs/plans/2026-08-22-phase-1b-
  implementation-plan.md`'s Task 10 section) — adding them would mean
  designing four more subsystems' worth of Azure equivalents (an AKS-
  hosted Keycloak cluster, a managed database or blob-backed Metabase, an
  Azure Monitor OTLP ingestion pipeline) that this portfolio project has
  no way to verify by actually applying. `portal-api`'s Container App
  therefore doesn't set `CANOPICA_KEYCLOAK_*_JWKS_URI` or
  `CANOPICA_OTLP_TRACES_ENDPOINT` — a real deployment building on this
  reference would need to add both.
- **Private networking.** The Postgres Flexible Server is
  `public_network_access_enabled = true` with no delegated subnet or
  private DNS zone. A real deployment would put this behind VNet
  integration and private endpoints (see the resource's own upstream
  example for the shape of that) — left out here so this config's
  resource list matches the plan's stated scope instead of growing into a
  full network design exercise.
- **Identity-based ACR pull.** Container Apps authenticate to the
  registry with the registry's own admin credentials
  (`admin_enabled = true`), not a managed identity + `AcrPull` role
  assignment. Simpler to read in a config that's never applied; a real
  deployment should use identity-based pull instead, per Azure's own
  guidance against admin credentials.
- **A real subscription, a real state backend, real secrets.** No
  `backend` block, no `subscription_id`, no committed `.tfvars`. Applying
  this for real means supplying all three yourself.

## The `usgovcloud` swap

The data this system is modeled around — income data handled with
FTI-style safeguards, Medicaid-adjacent health data from Phase 5 — is
exactly the category real state systems run in **Azure Government**
rather than commercial Azure (design doc §3.7). Azure Government isn't
self-service: provisioning it requires the tenant to already be a
verified U.S. government entity or an approved contractor, so this
personal project cannot actually run in it. This configuration is written
to be Azure-Government-compatible instead, and the swap is exactly two
provider arguments (`providers.tf`), nothing else in this configuration
changes:

```hcl
provider "azurerm" {
  environment   = "usgovernment"
  metadata_host = "management.usgovcloudapi.net"
  # ...
}
```

Pair it with a `usgovcloud` region for `var.location` (e.g.
`usgovvirginia`) and Government-cloud SKU availability for the resources
above — some SKUs and preview features (Container Apps' newer workload
profiles among them) land in Government cloud later than commercial
Azure, so verify current availability against Microsoft's own
documentation before relying on this for a real Gov-cloud deployment.

## Running it for real

Never done in this project, but for the record:

```bash
cd infra/azure
terraform init
terraform plan \
  -var="portal_api_image=<registry>/portal-api:<tag>" \
  -var="portal_web_image=<registry>/portal-web:<tag>" \
  -var="airflow_image=<registry>/airflow:<tag>"
terraform apply
```

`terraform init` needs a real Azure subscription (`az login` or a service
principal) and a real backend for state — an Azure Storage Account
container is the standard choice, deliberately not configured here since
committing a backend config that points at infrastructure this project
doesn't have would be worse than leaving it unconfigured.
