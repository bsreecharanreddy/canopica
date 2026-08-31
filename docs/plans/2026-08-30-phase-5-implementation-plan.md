# Phase 5 — Cloud Realization: Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for
> tracking. Execute tasks in order, one commit per completed task,
> `docs/STATUS.md` updated in that same commit (CLAUDE.md,
> "Conventions"). Run the `canopica-task-checkpoint` skill's gate
> (`make test`, `make lint`, STATUS.md, one commit) after each task.
> **Neither task's real-money step (Task 1's account signup, Task 2's
> `terraform apply`) runs without the user's explicit, live go-ahead at
> execution time** — this plan being approved is not that go-ahead. Same
> posture this project already holds for the Azure CI runner (never
> auto-apply infrastructure changes without an explicit signal).

**Goal:** Two real, live cloud-deployment proofs — the existing dbt
project actually running on Databricks, the existing reference Terraform
actually applied to Azure/Fabric — each captured as real screenshots.
This is Phase 5's entire build scope. Domain expansion (TANF/Medicaid)
and correspondence/interfaces breadth beyond SNAP are both **stated, not
built** extension points (`docs/STATUS.md`'s decisions table,
2026-08-30) — statable directly in an interview, no code or plan task
needed.

**Spec:** `docs/design/2026-08-21-full-system-and-phased-roadmap.md` §5
(what), `docs/STATUS.md`'s decisions table (both Phase 5 scope-narrowing
decisions and the two now-resolved open questions this plan answers),
`docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md` (where
the real findings from this plan get folded back in — see each task's
last step).

**Starting point, confirmed against the actual repo state before writing
this plan, not assumed:**

1. **`data-platform/dbt/canopica_warehouse/profiles.yml` has one target
   today, `local` (DuckDB).** No Databricks target exists — Task 1 adds
   one, additively; the `local` target and every existing test stays
   untouched.
2. **`infra/azure/`'s reference Terraform (excluding `infra/azure/
   ci-runner/`, a separate, already-applied, always-needed CI resource —
   not part of this demo) creates a real, non-trivial footprint**: a
   resource group, Key Vault (+ a secret), Postgres Flexible Server (+ 3
   databases), a Log Analytics workspace (+ diagnostic setting), a
   Container Registry, a Container App Environment, and four Container
   Apps (`api`, `ui`, `airflow-webserver`, `airflow-scheduler`).
   Keycloak, Metabase, OpenSearch, and the observability stack are
   **deliberately absent** from this reference Terraform (README's own
   "Honest limitations" section already says so) — so a fully
   login-capable, click-through demo is not this phase's bar. A real,
   provisioned-for-real infra footprint, screenshotted, is.
3. **Both real cloud resources here bill continuously once created** —
   Postgres Flexible Server and Container Apps have no deallocate-between-
   runs state, unlike the CI runner's VM. This plan follows the same
   apply → screenshot → destroy-immediately discipline this project
   already learned the hard way from the CI runner's own NAT Gateway
   lesson (`docs/STATUS.md`'s open questions: "$36/month continuously...
   affordable only against free-trial credit").
4. **Databricks Community Edition no longer exists.** Two current, real
   offerings replace it: **Free Edition** (permanent, $0, serverless-only,
   quota-limited, no credit card) and a separate 14-day full-platform
   **Free Trial**. Free Edition is the better fit here — no expiry/billing
   clock on a portfolio artifact — but whether `dbt-databricks` actually
   runs cleanly against its serverless-only SQL warehouse is a genuine,
   still-open unknown. That's this plan's Task 1, not a settled fact.
5. **Microsoft Fabric's free trial is a separate signup from the Azure
   $200/30-day credit**, not part of it — its own 60-day trial (64 CU
   capacity, 1TB OneLake, no credit card), activated in-app. Task 2 keeps
   this as its own step rather than assuming it rides along with the
   Terraform apply.

---

## Task 1: Databricks Free Edition — a real dbt run

**Files:**
- Modify: `data-platform/dbt/canopica_warehouse/profiles.yml` (+ a
  `databricks` target), `dbt_project.yml` (+ target-gated seeds config),
  `models/bronze/sources.yml` (+ per-target schema override),
  `macros/is_pii_column.sql` (+ adapter dispatch)
- New: `data-platform/databricks-adapter/` (isolated `dbt-core`/
  `dbt-databricks` pair — **not** `data-platform/pyproject.toml` as
  originally planned; see Step 2's note), `data-platform/dbt/
  canopica_warehouse/seeds/bronze/*.csv`, `docs/cloud-demo/databricks-*.png`
  (real screenshots)
- Modify: `README.md` (the "Honest limitations" / tech-stack sections —
  from "documented, never applied" to "applied for real, screenshots
  below"), `docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`
  (record what actually ported and what didn't, honestly)

- [x] **Step 1: Sign up for Databricks Free Edition.** Done by the user
      directly. Resolved the plan's own flagged unknown: the serverless SQL
      warehouse works, but only with an isolated dbt-core/dbt-databricks
      pair — see Step 2.
- [x] **Step 2: Add a `databricks` dbt profile target.** Done, but not as
      planned: adding `dbt-databricks` to `data-platform/pyproject.toml`
      directly is impossible — every `dbt-databricks` release (checked
      through the `2.0.0rc1` prerelease) caps `dbt-core` below `1.12.1`,
      while this project's DuckDB `local` target already pins `1.12.3`. A
      real, unresolvable version conflict, not a dialect issue. Fixed with
      a dedicated `data-platform/databricks-adapter/` project (isolated
      venv, `dbt-core==1.12.0` + `dbt-databricks==1.12.4`), the same
      isolated-venv-by-directory shape already used for `ai/`'s Airflow
      `BashOperator`s. Token lives in `.env` (gitignored), as planned.
- [x] **Step 3: Run `dbt build --target databricks` for real.** Done, with
      one further real correction: bronze's `source()` sourcing depends on
      a `dbt-duckdb`-only feature (`meta.external_location`/`delta_scan`)
      with no cross-adapter equivalent — "reuse the existing synthetic-data
      seed path" became a real, small, hand-built `dbt seed` slice
      (target-gated so `local` is provably untouched), not the synthetic
      generator itself. One genuine dialect gap found and fixed:
      `is_pii_column`'s `SIMILAR TO` isn't valid Databricks SQL at all
      (parser syntax error, not a behavior difference) — dispatches to
      `RLIKE` there now, `local`'s output verified byte-identical.
      **Result**: 4 tables, 45 tests, PASS=51 ERROR=0, real numbers
      matching the seed exactly. See STATUS.md's verification log for the
      full account.
- [x] **Step 4: Capture real screenshots.** Done —
      `docs/cloud-demo/databricks-unity-catalog.png`,
      `databricks-sql-result.png`, `databricks-sql-result-scrolled-right.png`.
- [x] **Step 5: Record the real result.** Done — STATUS.md, the tradeoffs
      doc (Transformation and Compute-engine rows), and README all updated
      in this task's commit with the real, verified result, including both
      real workarounds (isolated adapter env, seeded bronze) — not just the
      success path. `make test`/`make lint` confirmed still green (this
      task is additive; the `local` target's own behavior is unchanged,
      proven via `dbt list --resource-type seed --target local` returning
      zero nodes and a byte-identical PII-macro compile).

## Task 2: Azure free trial + Microsoft Fabric — a real Terraform apply

**Files:**
- Modify: `infra/azure/` (only if a real `terraform apply` surfaces a bug
  the validate-only history never exercised — same posture Phase 4's own
  live-verification tasks already established: fix what a live run
  actually finds, don't pre-guess it)
- New: `docs/cloud-demo/azure-*.png`, `docs/cloud-demo/fabric-*.png`
- Modify: `README.md`, `docs/STATUS.md`,
  `docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`

- [x] **Step 1: Confirm the real subscription state first.** Portal check
      — a fresh free-trial signup or the existing CI-runner subscription's
      remaining credit/days — don't assume either. **Needs the user's
      direct confirmation before anything is applied.** Done — confirmed
      via `az account subscription show` (`quotaId: FreeTrial_2014-09-01`).
- [x] **Step 2: `terraform plan`, reviewed, then `terraform apply` for
      real.** This is the plan's one real-money step — explicit go-ahead
      required at execution time, per this doc's own header. Done, staged
      (resource group/ACR first, then images, then full apply).
- [x] **Step 3: Capture real screenshots.** The resource group overview,
      the running Container Apps, the Postgres Flexible Server — proof the
      infra genuinely provisions, not just `validate`/`fmt`-clean in CI.
      Done — `docs/cloud-demo/azure-*.png` (7 images), PII-redacted.
- [x] **Step 4: Destroy immediately after capturing screenshots, same
      session.** `terraform destroy`, then confirm in the portal that
      nothing continuously-billed remains. **Not deferred, not "later" —**
      Postgres Flexible Server and Container Apps both bill continuously
      with no deallocate state, unlike a VM. Done — confirmed via
      `az group exists` (`false`) and `terraform state list` (empty).
- [x] **Step 5: Separately, sign up for the Microsoft Fabric free trial**
      (60 days, no credit card — a distinct signup from the Azure trial,
      per "Starting point" item 5) and capture one real screenshot of the
      existing TMDL semantic model (`reporting/semantic-model/`) published
      to / viewed in Fabric. Worked out live against this repo's own code
      (`data-platform/src/canopica_data/serving/materialize.py`,
      `config.py`, `infra/postgres/init/01-databases.sql`) rather than
      assumed, because two real constraints surfaced during research:
      Fabric's trial requires a work/school (Entra ID) identity, not a
      bare personal email (Microsoft's own documented workaround reuses
      an existing Azure account — see
      [free-trial-account-personal-email](https://learn.microsoft.com/en-us/fabric/fundamentals/free-trial-account-personal-email));
      and the On-premises Data Gateway (the normal way Fabric reaches a
      local Postgres) is Windows-only, confirmed no macOS support, so
      pointing Fabric at `make up`'s local Compose Postgres isn't viable
      from this dev machine. Sub-steps:
      - **5a. Scoped Terraform apply — Postgres only, not the full Task 2
        stack.** This demo needs a reachable serving database, not a
        running API/UI/Airflow, so `-target` is scoped to
        `azurerm_postgresql_flexible_server_firewall_rule.azure_services`
        and `azurerm_postgresql_flexible_server_database.serving` (pulls
        in their dependencies: the server, the resource group, the
        generated admin password). Deliberately excludes Key Vault — the
        server's `administrator_password` reads directly from
        `random_password.postgres_admin.result`, never through the
        vault, so Key Vault isn't a dependency of this target set and
        skipping it avoids repeating Task 2's Key Vault RBAC
        data-plane/management-plane teardown gap for a resource this
        demo doesn't need. Also excludes ACR, Container Apps, Log
        Analytics, and the `pgcrypto` extension config (serving-layer
        tables don't need it — only the operational database's audit
        chain does). `api_image`/`ui_image`/`airflow_image` have no
        defaults and Terraform resolves all variables before honoring
        `-target`, so the apply needs placeholder `-var` values for
        those three even though their resources aren't targeted.
      - **5b. One more firewall rule, for the local dev machine's public
        IP**, via `az postgres flexible-server firewall-rule create`
        (not Terraform — machine-specific, added and removed outside the
        committed config, same posture as every other live-only fix this
        task found). Needed so `psql`/the materialize step below can
        reach the server directly from this laptop.
      - **5c. Bootstrap SQL against the new server**, as the admin login,
        creating `canopica_app` and a read-only `canopica_analytics_ro`
        role — mirroring exactly what `infra/postgres/init/
        01-databases.sql` already does locally for the serving layer
        (schema ownership, `select`-only default privileges), not a new
        design.
      - **5d. Run the existing local pipeline unchanged** — `make up`,
        `make seed`, a real determination, `make pipeline` through the
        DuckDB gold build — then re-run only the materialize step with
        `CANOPICA_SERVING_DSN` pointed at the Azure Postgres FQDN instead
        of `localhost`. `materialize_gold()` already takes `serving_dsn`
        as a plain argument, so this is a one-env-var swap, not a code
        change.
      - **5e. Import the semantic model in Fabric** via its direct cloud
        PostgreSQL connector (no gateway needed for a publicly-reachable
        Azure PaaS host) using `canopica_analytics_ro`, `ServingHost` =
        the Azure FQDN — the same steps `reporting/powerbi/README.md`
        already documents, run in a Fabric workspace instead of plain
        Power BI Service. Build one report card against `Determinations`
        / `Eligible Rate` / `Average Benefit` so the screenshot shows
        real numbers, not an empty model shell.
      - **5f. Screenshot, PII-redact the same way as the other 7, save to
        `docs/cloud-demo/fabric-*.png`.**
      - **5g. Teardown**: delete the temporary local-IP firewall rule,
        `terraform destroy` this scoped deployment, confirm
        `az group exists` → `false`. The Fabric trial capacity itself
        needs no teardown — it's Microsoft's own trial allocation, not
        billed against the Azure subscription.

      **Real outcome, done for real, one honest scope correction along
      the way**: Fabric trial *activation* itself failed —
      `"A Fabric trial isn't available for your account"` — root-caused
      to Microsoft's own documented ~90-day new-tenant restriction on
      trial capacity, a structural block no retry fixes. What the trial
      granted instead (a Power BI Individual trial) was already
      documented as sufficient for this exact import
      (`reporting/powerbi/README.md`: "no Premium/Fabric capacity
      required"), so 5e ran against Power BI Service instead of Fabric
      proper — same real data, same real screenshot requirement, one
      real screenshot short of literally saying "Fabric" on the
      Microsoft-product-branding level. 5a–5d and 5g ran exactly as
      planned. Full story, including the two further gateway-shaped
      gaps found in 5e (a Fabric-capacity-gated Mirroring item, and the
      TMDL folder import's own on-prem-gateway requirement), in
      `docs/STATUS.md`'s verification log.
- [x] **Step 6: Record the real result.** `docs/STATUS.md`'s verification
      log, the tradeoffs doc, and the README — screenshots plus what was
      actually observed, including any real gap the live apply found
      (e.g. anything that doesn't work without Keycloak/Metabase, already
      an accepted, documented limitation — confirm it stays accurately
      described, don't silently overstate what the demo proves). Full
      suite still green. Done for Steps 1-4's real gaps (region capacity,
      firewall, extension allow-list, nginx DNS, Airflow init, Key Vault
      RBAC teardown) and now Step 5's (Fabric trial capacity blocked by
      the 90-day new-tenant restriction, Power BI Service completed
      instead) — all recorded in `docs/STATUS.md`'s verification log.

---

## Phase 5 definition of done

- [x] Both tasks committed, each with its own real screenshot evidence and
      a green full-suite run.
- [x] `docs/STATUS.md` reflects Phase 5 as done, at the same task
      granularity every earlier phase already uses.
- [x] README's "Honest limitations" and tech-stack sections updated with
      the real screenshots and an accurate statement of what's now proven
      versus what's still a documented limitation — no overstatement.
- [x] No continuously-billed Azure resource left running after Task 2 —
      verified in the portal, not assumed from the `terraform destroy`
      exit code alone.

## Deferred out of Phase 5, on purpose

- **Domain expansion (TANF/Medicaid)** — stated-not-built extension point
  (`docs/STATUS.md`'s decisions table).
- **Correspondence and interfaces breadth beyond SNAP** — likewise
  stated-not-built (same table, decided alongside this plan).
- **A fully login-capable cloud demo.** `infra/azure/`'s reference
  Terraform deliberately excludes Keycloak/Metabase/OpenSearch/the
  observability stack (README's own documented limitation, unchanged by
  this phase). This phase proves the infra provisions and the data
  platform runs on real cloud targets — not a complete, cloud-hosted,
  clickable product.
