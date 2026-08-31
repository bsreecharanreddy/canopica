---
name: canopica-code-review
description: Use after writing or modifying code for a Canopica task, before calling it done — reviews for this project's own accumulated, non-obvious conventions (migration numbering, audit-event/CHECK-constraint sync, transactional-outbox correctness, shared-Postgres test isolation, the bronze/silver/gold path for a new operational table, the real-agency naming ban, AI-boundary constraint conformance, scope discipline) that no generic reviewer would know to check, since each is grounded in a mistake this project has actually made.
---

# Canopica code review

A generic reviewer (a third-party agent, a first read-through) catches
general code quality. It cannot catch a convention that only exists
because this specific project got burned by its absence once — that's
what this skill is for. Complementary to, not a replacement for:
`canopica-task-checkpoint` (the process/commit gate — full suite,
STATUS.md, one commit per task) and the `canopica-security-auditor`
subagent (authorization/PII/AI-trust-boundary specifically). This skill's
job is the code's *content* against this project's own house rules.

## 1. Migration numbering: widen once per real need, in landing order

Flyway's `outOfOrder` is not enabled (`application.yml` has no such
setting), so a migration number reserved now for a not-yet-built task
breaks validation the moment that task's real file lands out of sequence.
This has already happened twice: `V18`'s own comment documents correcting
"the Phase 3 implementation plan's own Task 2 file list" for claiming a
single migration would widen `audit_event`'s CHECK for both that task's
event type *and* a future task's `NOTICE_*` types; Phase 4 repeated the
identical mistake in its own plan doc, corrected the same way (see
`V24`'s comment). Check: does a new migration widen a CHECK constraint,
enum, or similar for more than the *current* task's own real need? Does
any plan doc reserve a version number for a task that hasn't landed yet?

## 2. A new `AuditEventType` needs two things, not one

If new code appends an audit event with a type the enum doesn't have yet:
(a) `AuditEventType.java` gets the new constant — **even if only the
Python worker ever writes that event**, because `JdbcAuditService
#findBySubject` deserializes `event_type` back into this enum on every
read, and throws on an unrecognized value the first time the case
audit-trail endpoint reads one back; (b) a migration widens
`audit_event_event_type_check` for that one new value, following rule 1
above. Missing either half is a real gap, not a style nit — (a) breaks
reads, (b) breaks writes.

## 3. Transactional-outbox: does the enqueue actually share the write's transaction?

Constraint 17 (every phase's plan doc restates it): a `pgmq.send(...)`
call meant to fire only when its triggering write commits must run
*inside that write's own `@Transactional` scope*, not just textually
near it. Two real, distinct ways this has broken silently in this
project:

- **Spring AOP self-invocation.** `@Transactional` is proxy-based — a
  method on the same class calling another `@Transactional` method via
  `this.foo(...)` bypasses the proxy entirely, silently downgrading the
  guarantee to two separately auto-committed statements with nothing
  externally observable to tell you it happened. Found for real in
  `QcSamplingService.runSample()` calling `this.sampleOne(...)` directly
  — fixed via `@Lazy` self-injection before any test caught it, but it
  could as easily have shipped. Check any class where a public method
  loops and calls a `@Transactional` method on itself.
- **JDBC statement-vs-function mismatch.** `PgmqService.send()` originally
  used `jdbc.update(...)` for `select pgmq.send(?, ?::jsonb)` — a SQL
  function that *returns* a value, which the Postgres JDBC driver's
  `executeUpdate()` rejects outright. This was live in production the
  moment any Java caller first exercised it (Python's `psycopg` has no
  equivalent restriction, so the worker side never revealed it). Check:
  does a new raw-SQL call via `JdbcTemplate` match `update` vs.
  `queryForObject`/`queryForList` to whether the statement returns a
  result set?

## 4. Test assertions against the shared Testcontainers Postgres

`AbstractPostgresTest`'s container (Java) and `migrated_settings` (Python
worker) are both effectively singleton, never-truncated instances shared
across every test method — and, for Java, across every test *class* in
the fork. `AuditChainTest`'s own comment states the resulting rule
directly: "an unscoped count is really 'how many \[rows\] has the whole
suite made before this test happened to run,' not this test's own claim."
A count/size assertion needs to be scoped to something the test itself
created (a specific id, a specific determination) — never a bare
`count(*)` or `.size()` against a whole table/event type. This is not
hypothetical: this same session's own `test_qc_summary_consumer.py`
shipped exactly this bug on the first pass (a global
`count(*) from audit_event where event_type = 'QC_DISCREPANCY_FLAGGED'`
collided with a row an earlier test in the same file had already
written) and was only caught by actually running the suite. Check every
new test's own assertions for this shape before trusting a green run.

## 5. A new operational table dbt/reporting cares about needs its full path

Bronze → silver → gold isn't automatic. A new table needs: an entry in
`extract.py`'s `ALL_TABLES`, a `bronze/sources.yml` source entry, a
silver `fct_`/`dim_` model (the "latest by `_ingested_at`" dedup pattern
if the table is mutable), and `silver.yml`/`gold.yml` column-level
`meta: { classification: ... }` tags. `fraud_risk_score` shipped in Task
2 with none of this — Task 3 found and fixed the gap only because
`mart_fairness_audit`'s own fraud-triage axis needed the data. Check: did
this task add or modify an operational table gold-layer reporting reads
from (directly or via a future mart), and does its bronze/silver path
actually exist yet, or is it silently assumed for later?

## 6. Never name a real agency, program, or systems integrator

CLAUDE.md's own rule, restated because it's easy to violate by accident
in a realistic-sounding doc comment or synthetic fixture: no real state
health & human services agency, no real state benefits program name, no
real consulting firm/SI, anywhere in code, docs, comments, or commit
messages. Technology vendors and products (Databricks, Power BI,
Keycloak, Azure, Drools, USDA FNS as the real *data source* being cited
for policy figures) are explicitly fine — don't over-scrub those. Check
new prose specifically, since code identifiers rarely trip this.

## 7. AI call sites against the currently-active phase's own constraints

Every phase's plan doc states its own numbered constraints (e.g. Phase
4's 19–23: no auto-adjudication, the fraud model's feature-proxy
exclusion, the QC summary's diff-only grounding, no SOP-mining write
path, demographic PII handling). A new or modified LLM call site should
be checked against whichever of these actually apply — in particular,
whether a deterministic post-check gates the model's output the way
`correspondence/validate.py` and `qc_assistant/validate.py` already do,
per the governing principle: AI drafts/flags/explains, it never decides.
An LLM call with no grounding/deterministic check before its output
reaches a human or gets persisted is the gap to flag.

## 8. Scope discipline

CLAUDE.md's Conventions section, restated as a review check: does the
diff reformat, restyle, or "improve" adjacent code, comments, or
unrelated lines while touching a file for something else? Does it match
the surrounding style even where you'd have written it differently? If
pre-existing dead code was noticed along the way, is it *named* rather
than silently deleted — unless the current change is specifically what
made it unused?

## What this skill doesn't cover

Full-suite-green, STATUS.md same-commit, one-commit-per-task, the
README diagram, and the "did a call site grow a new external CI
dependency" check are all `canopica-task-checkpoint`'s job — don't
duplicate them here. Authorization/IDOR-class bugs, `SecurityConfig`
matcher coverage, PII/tokenization, and secret hygiene are the
`canopica-security-auditor` subagent's job — invoke that separately
rather than re-deriving its checklist inline.
