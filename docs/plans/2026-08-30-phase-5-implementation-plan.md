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
  `databricks` target)
- Modify: `data-platform/pyproject.toml` (+ `dbt-databricks` adapter)
- New: `docs/cloud-demo/databricks-*.png` (real screenshots)
- Modify: `README.md` (the "Honest limitations" / tech-stack sections —
  from "documented, never applied" to "applied for real, screenshots
  below"), `docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`
  (record what actually ported and what didn't, honestly)

- [ ] **Step 1: Sign up for Databricks Free Edition.** Portal-only, no
      code — **needs the user directly**, not something to automate. While
      there, confirm live what the serverless SQL warehouse / Unity
      Catalog experience actually looks like — this resolves the one
      unverified claim in "Starting point" item 4 above.
- [ ] **Step 2: Add a `databricks` dbt profile target.** `dbt-databricks`
      adapter, pointed at the Free Edition serverless SQL warehouse's HTTP
      path + a real personal access token — the token lives in `.env`
      (gitignored), same pattern every other credential in this project
      already uses, never committed. Catalog/schema naming matches this
      project's existing conventions.
- [ ] **Step 3: Run `dbt build --target databricks` for real**, against a
      small seeded slice (reuse the existing synthetic-data seed path, not
      the full local warehouse — this is a proof of portability, not a
      second production copy). Resolve whatever DuckDB → Databricks
      SQL/Delta dialect differences actually surface; if something
      genuinely doesn't port cleanly, that's a real, honestly-recorded
      finding for Step 5, not something to paper over.
- [ ] **Step 4: Capture real screenshots.** Unity Catalog showing the
      built tables, and a query result against one real gold mart (e.g.
      `mart_determination_outcomes`) run from the Databricks SQL editor.
- [ ] **Step 5: Record the real result.** `docs/STATUS.md`'s verification
      log, the tradeoffs doc (a `≈`/`~` fidelity mark for "runs on the
      real target platform, under free-tier limits" is now backed by
      evidence, not aspiration), and the README screenshot section — all
      including anything that needed a workaround, not just the success
      path. `make test`/`make lint` still fully green (this task is
      additive; the `local` target's own behavior doesn't change).

## Task 2: Azure free trial + Microsoft Fabric — a real Terraform apply

**Files:**
- Modify: `infra/azure/` (only if a real `terraform apply` surfaces a bug
  the validate-only history never exercised — same posture Phase 4's own
  live-verification tasks already established: fix what a live run
  actually finds, don't pre-guess it)
- New: `docs/cloud-demo/azure-*.png`, `docs/cloud-demo/fabric-*.png`
- Modify: `README.md`, `docs/STATUS.md`,
  `docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`

- [ ] **Step 1: Confirm the real subscription state first.** Portal check
      — a fresh free-trial signup or the existing CI-runner subscription's
      remaining credit/days — don't assume either. **Needs the user's
      direct confirmation before anything is applied.**
- [ ] **Step 2: `terraform plan`, reviewed, then `terraform apply` for
      real.** This is the plan's one real-money step — explicit go-ahead
      required at execution time, per this doc's own header.
- [ ] **Step 3: Capture real screenshots.** The resource group overview,
      the running Container Apps, the Postgres Flexible Server — proof the
      infra genuinely provisions, not just `validate`/`fmt`-clean in CI.
- [ ] **Step 4: Destroy immediately after capturing screenshots, same
      session.** `terraform destroy`, then confirm in the portal that
      nothing continuously-billed remains. **Not deferred, not "later" —**
      Postgres Flexible Server and Container Apps both bill continuously
      with no deallocate state, unlike a VM.
- [ ] **Step 5: Separately, sign up for the Microsoft Fabric free trial**
      (60 days, no credit card — a distinct signup from the Azure trial,
      per "Starting point" item 5) and capture one real screenshot of the
      existing TMDL semantic model (`reporting/semantic-model/`) published
      to / viewed in Fabric.
- [ ] **Step 6: Record the real result.** `docs/STATUS.md`'s verification
      log, the tradeoffs doc, and the README — screenshots plus what was
      actually observed, including any real gap the live apply found
      (e.g. anything that doesn't work without Keycloak/Metabase, already
      an accepted, documented limitation — confirm it stays accurately
      described, don't silently overstate what the demo proves). Full
      suite still green.

---

## Phase 5 definition of done

- [ ] Both tasks committed, each with its own real screenshot evidence and
      a green full-suite run.
- [ ] `docs/STATUS.md` reflects Phase 5 as done, at the same task
      granularity every earlier phase already uses.
- [ ] README's "Honest limitations" and tech-stack sections updated with
      the real screenshots and an accurate statement of what's now proven
      versus what's still a documented limitation — no overstatement.
- [ ] No continuously-billed Azure resource left running after Task 2 —
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
