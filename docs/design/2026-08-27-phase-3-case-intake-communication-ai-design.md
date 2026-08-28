# Canopica — Phase 3 Case Intake & Communication AI: Design Decisions

## 1. Scope recap

Phase 3, per the roadmap doc (§ Phase 3 — Case Intake & Communication AI):
Intelligent Document Intake, AI-drafted correspondence, and translation/
localization of the UI and correspondence. Same governing principle as
everywhere else in this repo: AI drafts, flags, and explains; deterministic
systems and human reviewers own every binding decision. This doc settles
the real forks — the mechanism decisions an implementation plan can't be
written without — the same way `2026-08-23-phase-2-policy-intelligence-
analytics-ai-design.md` did for Phase 2. It does not plan file-by-file;
that's the implementation plan's job, next.

Phase 3 is genuinely greenfield in a way Phase 2 wasn't: Phase 2 built on
infrastructure that already existed (OpenSearch, Ollama, the operational
Postgres). Confirmed against the actual repo state before writing this
doc — none of the following exist yet: an object store, the `pgmq`
extension, any async background-worker process, a `NOTICE` table, or a
UI translation library. Every one of those is a real decision below, not
an assumption carried in from elsewhere.

Checked against current (2026) industry practice for LLM document
classification/extraction, LLM-drafted-document validation patterns, and
transactional message-queue reliability before being finalized — three
real findings came out of that pass, noted inline where they apply rather
than folded in as if they were the original brainstorm's own conclusions:
a stricter-than-industry-norm human-confirmation gate for extracted data
(§2.3), a template-filling (not free-drafting) mechanism for correspondence
(§2.4), and pgmq's same-transaction enqueue giving outbox-pattern
reliability for free, which the existing pgmq decision row didn't
previously state (§2.2).

## 2. Decisions

### 2.1 Object storage

**MinIO** (S3-compatible), already decided at the tier level in the
tech-stack tradeoffs doc's Object storage row (production equivalent:
ADLS Gen2/S3), but never actually stood up — `infra/docker-compose.yml`
has no such service today. Added here as a genuinely new Phase 3
component, not re-litigated: a `minio` service, one bucket
(`canopica-documents`), credentials via the same local-dev environment-
variable pattern every other service in the compose file already uses.

Uploaded documents are stored exactly as uploaded — no OCR/extraction
output overwrites the original — with the object key derived from the
`program_request_id` and a generated document id, never from anything
applicant-supplied, so a crafted filename can't traverse or collide.
`document` (new table, §2.6) is the system-of-record pointer: object key,
content type, uploaded-by, uploaded-at. The object itself is never deleted
by this system (matches the tradeoffs doc's already-stated "documents are
stored, not *managed* — no retention schedule, no legal hold, no records
disposition" limitation; not revisited here).

**Addendum, found at Task 1 implementation time, not the original
brainstorm**: MinIO's community edition was archived by its own
maintainers in 2026 (maintenance mode Dec 2025 → "no longer maintained"
Feb 2026 → GitHub repo archived; the company moved to a paid product,
AIStor, instead). The server code was never relicensed — still AGPLv3,
still free to run — so this doesn't change the "$0, self-hosted" cost
posture the tradeoffs doc's Object storage row already commits to, only
its maintenance status. Weighed against a maintained community fork
(e.g. `pgsty/minio`) and a different product entirely (SeaweedFS, Garage):
kept MinIO, pinned to its last *actually published* Docker Hub release
(`RELEASE.2025-09-07T16-13-09Z`, verified live against Docker Hub's own
tag API 2026-08-28 -- the next release, `RELEASE.2025-10-15T17-29-55Z`,
was announced but never pushed as a container image at all; a core
maintainer stated post-announcement that MinIO now ships source only),
because this is local/CI-only infrastructure never exposed to the internet — the same risk posture this
project already accepts for local Postgres/Keycloak (no TLS, dev-mode
credentials) — and it avoids taking on either a newer, less-proven fork
or a larger design revision this late. Stated explicitly rather than
silently pinning a dead project's last tag; revisit if this project ever
needs object storage on a surface that's actually internet-facing.

### 2.2 Async worker & pgmq

**pgmq** was already decided as the queue mechanism (roadmap §3.3,
tradeoffs doc §4.11) but never implemented — confirmed the current
`postgres:16-alpine` image doesn't bundle the extension, and no
background-job-processing code exists anywhere in this repo today
(determinations run synchronously, inline with the API call that triggers
them). Phase 3 is the first real consumer, so this is where the mechanism
actually gets built, not just documented.

**Postgres image**: swap to an image that bundles the `pgmq` extension
(e.g. the official `pgmq`-enabled Postgres image) rather than hand-rolling
a custom Dockerfile layer — same "use the maintained thing" posture this
project already takes with `postgres:16-alpine` itself. Exact image tag
pinned at implementation time.

**Worker process language: Python**, not Java. Per CLAUDE.md's language
policy ("Python is the default for anything where the language is
genuinely open... Java/Spring stays where it earns its place... not to be
rewritten away elsewhere"), a queue-polling worker isn't API-surface or
DMN-evaluation — it's exactly the kind of infrastructure/tooling code the
policy hands to Python by default. Structured as its own small deployable
(`worker/` at the repo root, alongside `api/`, `ai/`, `data-platform/` —
not folded into `ai/`, since its job is orchestration — enqueue, dequeue,
retry, dead-letter — not model inference; it calls into `ai/`'s document-
classification and correspondence-drafting pipelines as a library, the
same way `api/`'s Java code never contains ML logic itself).

**Two queues**, matching the roadmap's own two Phase 3 features exactly:
`document_intake` and `correspondence_dispatch`. Kept separate rather than
one shared queue — different consumers, different failure/retry
semantics (a stuck document classification shouldn't back up notice
dispatch, or vice versa), and pgmq queues are cheap (`pgmq.create()`
against the same database) so there's no infrastructure cost to keeping
them apart.

**Reliability, a real finding from checking current practice**: because
`pgmq`'s queue tables live in the *same* Postgres database and the *same*
transaction as the operational tables, calling `pgmq.send()` inside the
same `@Transactional` boundary as the row it's about (a `document` insert,
an `eligibility_determination` commit) gets transactional-outbox
reliability for free — the enqueue can never succeed while the underlying
write rolls back, or vice versa, with no separate outbox table and no
CDC/relay process. A dedicated broker (Kafka/RabbitMQ, the tradeoffs
doc's stated production equivalent) would need that outbox-table-plus-
relay machinery explicitly to get the same guarantee; pgmq gets it as a
structural consequence of living inside Postgres. Worth stating in the
tradeoffs doc (§3 below) as a concrete strength of the existing pgmq
choice, not previously articulated.

**Consumer pattern**: `pgmq.read()` with a visibility timeout, then
`pgmq.delete()` only after the worker's own processing (classification,
or notice drafting) commits successfully — a message that crashes mid-
processing becomes visible again after the timeout and gets retried, not
silently lost. A message that fails repeatedly (retry count past a small
fixed limit) moves to pgmq's own archive rather than looping forever;
surfaced as a Grafana alert (§2.7), not silently dropped.

### 2.3 Intelligent Document Intake

**Pipeline**: upload (stored per §2.1, `document` row inserted, `pgmq.send`
to `document_intake` in the same transaction) → worker picks up the
message → text/layout extraction → LLM structured-output classification
+ field extraction against a Pydantic v2 schema (this project's existing
standard, per CLAUDE.md's Python conventions and every other AI service in
`ai/`) → a per-field confidence score → **worker review, always** → on
confirm, the confirmed values populate the relevant intake record
(`income_record`, `verification.status`, etc.) through the same insert/
update paths a caseworker's manual entry already uses — the AI pipeline
never writes directly to a case record.

**Extraction approach**: LLM-native structured extraction (a vision- or
text-capable model producing schema-validated JSON directly), not a
traditional OCR-then-regex-parse pipeline. Checked against current
practice: 2026 benchmarks and production guidance consistently favor
LLM-native parsing for this shape of document (forms, letters, checklists)
over reconstructing structure from raw OCR output, which loses layout
information the LLM can otherwise use directly. A lightweight OCR/text-
extraction pass still runs first for scanned (image-only) uploads, feeding
the LLM extracted text plus page images rather than replacing the LLM step.

**Confidence-gated review — a deliberate divergence from current industry
norm, stated explicitly rather than left implicit**: standard practice
elsewhere in 2026 (per the research pass) is to auto-apply high-confidence
extractions and route only a small minority (commonly cited around 1-5%)
to human review, using a trustworthiness/calibration score as the
routing signal. Canopica does not do this. **Every extraction gets worker
confirmation before it touches a case record, regardless of confidence
score.** The confidence score still does real work — it drives review-
queue prioritization and visual emphasis (a low-confidence field is
flagged for extra scrutiny) — but it never bypasses the gate. This
follows directly from the project's own governing principle (AI never
owns a binding decision) applied literally: a case record change is
binding in exactly the sense that principle means, so there is no
confidence threshold high enough to skip the human. Recorded here as a
considered choice against the industry default, not an oversight.

**Document types**, per the roadmap's own list: income reports, renewal
packets, work activity reports, verification-checklist documents. Each
upload is checked against that `program_request`'s own outstanding
`verification` rows (§3.4.1's existing entity, already tracking
`data_element`/`status`/`due_on`) — the classification step's job
includes proposing *which* outstanding verification a document satisfies,
not just what kind of document it is.

**Guardrails — indirect prompt injection, a real finding from the
research pass**: an uploaded document is untrusted content an applicant
(or, worse, someone impersonating one) fully controls — adversarial text
hidden in PDF metadata, off-canvas regions, or a scanned image is a
documented, live attack class against exactly this kind of pipeline in
2026. The mitigation here isn't a content filter (those are documented as
unreliable against this attack class) — it's architectural: this pipeline
has no tool-calling ability and takes no autonomous action, so a
successful injection's blast radius is bounded to corrupting an
*extracted field value* (e.g. an inflated income figure), which the
mandatory worker-confirmation gate above catches before it reaches a case
record. Same trusted/untrusted content boundary Phase 2's design doc
already established for retrieval (§2.2 there) — applied here to a new,
higher-stakes untrusted-content surface, and the reason the review gate
is load-bearing as a *security* control, not only a UX one.

### 2.4 AI-drafted correspondence

**Trigger**: after an `eligibility_determination` transaction commits,
`pgmq.send` to `correspondence_dispatch` in that same transaction (§2.2's
outbox guarantee) — drafting never holds up the binding decision, exactly
as the roadmap specifies.

**Mechanism — template-filling, not free-form generation-then-validation**,
a real revision from the original brainstorm after checking current
practice: the research is fairly consistent that grounding generation in
verified source content and a fixed structure outperforms free drafting
for anything compliance-adjacent, and surfaces unfilled/ambiguous slots
explicitly rather than requiring after-the-fact detection. Concretely: a
fixed notice template per `notice_type` (approval, denial, pending-
verification) with named slots; the LLM's job is filling those slots —
the plain-language explanation of *why*, composed from the determination's
own trace (§3.4.1's `determination_trace`, deterministic, never
recomputed) and the audit trail — not drafting the notice's structure or
its numbers. Every dollar amount, date, and program name in a filled
template is substituted programmatically from the determination record
itself, never generated by the LLM — the same "the LLM composes
explanation of numbers that are already correct" boundary Phase 2's
Policy Q&A design doc (§2.2) already established for "why was I denied,"
applied here to the artifact that actually gets sent.

**Validation gate**, reusing Phase 2's eval-gate shape rather than
inventing a new one: a deterministic pre-check (every required template
slot filled; every number/date the draft asserts matches the determination
record's own value exactly — string/value equality, not LLM-judged) runs
before a human ever sees the draft, the same "cheap, zero-noise check
before spending a judge call" posture as §2.6 of the Phase 2 doc's
citation pre-check. A worker/admin then reviews the filled draft and
either approves (status → `APPROVED`, dispatch proceeds) or rejects
(status → `REJECTED`, no dispatch) — no path auto-sends. "Dispatch" itself
means rendering to PDF and recording the notice as sent (tradeoffs doc
§4.4, unrevisited: no print-and-mail vendor, no certified-mail tracking —
notices are generated, never actually delivered by this system).

### 2.5 Translation/localization — split into two different things

The roadmap's single bullet ("translation/localization of the UI and
correspondence") covers two mechanisms that shouldn't share one design:

- **UI string i18n**: a standard library (`react-i18next`, matching the
  existing React 19 + Vite stack) translating static UI copy from
  maintained translation files. Pure tooling, not an AI capability at
  all — no LLM involved, nothing for this doc's AI-safety sections to say
  about it.
- **Correspondence translation**: LLM-translated, but the translated
  draft goes through the *exact same* §2.4 validation gate and human
  review as the English draft — never a separate, less-reviewed path.
  The deterministic number/date check still applies (a mistranslated
  dollar amount is exactly the failure mode that check exists to catch,
  language notwithstanding).

### 2.6 Domain model additions

Two new tables, both referenced by the roadmap's own ER diagram (`NOTICE`)
or implied by its Phase 3 bullets (`document`) but never built:

- **`document`** (Java-owned, public schema — a system-of-record pointer,
  same tier as `verification`/`benefit_month`): `id`, `program_request_id`,
  `object_key` (MinIO), `content_type`, `uploaded_by`, `uploaded_at`,
  `classification_status` (`PENDING`/`CLASSIFIED`/`CONFIRMED`/`REJECTED`).
- **`notice`** (Java-owned, public schema): `id`, `program_request_id`,
  `determination_id` (FK to `eligibility_determination`), `notice_type`,
  `status` (`DRAFT`/`APPROVED`/`REJECTED`/`SENT`), `content` (the filled
  template), `template_version`, `language`, `validation_result` (jsonb —
  the deterministic pre-check's own output, kept for audit even after a
  human reviews), `approved_by`, `approved_at`, `sent_at`, `created_at`.
  Deliberately **one table with a status lifecycle**, not split into an
  advisory table plus a separate published table the way `ai.
  policy_qa_answer` sits apart from `eligibility_determination` — a
  Policy Q&A answer *explains* a determination but is never itself the
  thing sent to anyone, whereas a notice's draft content *is* the
  eventual artifact once approved, so there's one row's worth of state to
  track, not two independent entities. Closer in shape to `policy_
  parameter_proposal` (§2.3 of the Phase 2 doc) — a mutable row a human
  reviews and either advances or not — than to the qa_answer pattern.
  AI provenance (prompt version, generation model, generation params)
  lives directly on this table for the same reason, rather than in a
  separate `ai.*`-schema row.
- **New audit event types**: `DOCUMENT_UPLOADED`, `DOCUMENT_CLASSIFIED`,
  `NOTICE_DRAFTED`, `NOTICE_APPROVED`, `NOTICE_SENT` — extending
  `AuditEventType` (currently `APPLICATION_SUBMITTED`, `DETERMINATION_
  MADE`, `CASE_VIEWED`, `VERIFICATION_UPDATED`, `POLICY_PARAMETER_
  PUBLISHED`) the same way V16 already widened it once for Phase 2's
  parameter-publish event. Every one of these is a real, auditable
  case-affecting action — exactly what this table exists for.

### 2.7 Observability

Extends the existing OTel/Jaeger/Prometheus/Grafana stack, same posture
as Phase 2's design doc §2.8 — no new tool. The worker process (§2.2)
gets spans around each `pgmq.read`/classification/`pgmq.delete` cycle and
each drafting/validation cycle, using the same `gen_ai.*` semantic
conventions already applied to Phase 2's LLM calls (still experimental/
pre-1.0 as of this year — verify the current spec at implementation time,
same caveat Phase 2's doc already states). A new Grafana panel: pgmq
queue depth and archive (dead-letter) rate for both queues — the concrete
signal that a stuck consumer or a repeatedly-failing document is visible
operationally, not just to a worker digging through pgmq's SQL functions
by hand.

### 2.8 Stated defaults (not forks — recorded for completeness)

- **`worker/` directory layout**: new at the repo root, alongside `api/`,
  `ai/`, `data-platform/`, `ui/` — the roadmap doc's repo-layout section
  predates this decision and gets updated in the same commit as this
  doc's approval, not reopened here as a fork.
- **OCR/text-extraction library**: exact package pinned at implementation
  time against what's current and maintained then, not hardcoded in this
  doc — same "pin at implementation time" treatment Phase 2's doc already
  gives Ollama model tags.
- **Threat-model boundary** (uploaded documents untrusted, same as
  applicant-submitted free text in Phase 2 §2.2): already decided in
  roadmap §3.3; §2.3 above is its application to a new, higher-stakes
  content surface, not a new decision.

### 2.9 Cross-cutting AI architecture & safety patterns

- **Bounded pipelines, not autonomous agents** — unchanged from Phase 2
  §2.10, restated because it's the actual mitigation for §2.3's injection
  risk: document intake is upload→classify→extract→human-confirm, and
  correspondence is commit→draft→validate→human-approve→dispatch. Neither
  pipeline gives the LLM a tool-call loop or the ability to act on its
  own output.
- **Structured output, not free text** — the document-classification
  schema and the notice-template slot values are both Pydantic v2-
  validated before anything downstream consumes them, same standard as
  every other AI service in `ai/`.
- **Human confirmation with no confidence-based bypass** — §2.3's own
  finding, stated once here as the cross-cutting version of it: neither
  pipeline in this phase has an auto-apply path at any confidence level.
- **No new public/unauthenticated surface** — unlike Phase 2's public
  demo, both Phase 3 capabilities are reachable only by an authenticated
  caseworker (document review) or run entirely server-side (correspondence
  drafting, triggered by a determination, not a user request) — no new
  moderation/rate-limiting surface is needed for this phase.
- **Considered, deliberately deferred**: OCR confidence fusion across
  multiple extraction passes (the research surfaced parallel-extraction-
  plus-consensus-voting as a way to raise confidence-score quality itself
  — real, but additive scope for a later refinement, not needed given
  §2.3's every-extraction-gets-reviewed posture makes the confidence
  score advisory-only rather than gating); a structured feedback loop on
  notice-draft rejections feeding future template refinement (same
  category Phase 2's doc already deferred for Policy Q&A thumbs-up/down).

## 3. Tradeoffs doc — refinements this unlocks

- Strengthen the existing **Async task queue** row's rationale
  (currently states "decouples... from the request/determination path"):
  add that `pgmq.send()` inside the same transaction as the triggering
  write gets transactional-outbox reliability structurally, for free,
  which a dedicated broker would need explicit outbox-table-plus-relay
  machinery to match — a concrete strength, not previously stated.
- Refine the AI/Platform tier's existing **Document intake** and
  **Correspondence** rows (both already present, pre-dating this doc, at
  the tier level only) with the concrete mechanisms this doc settles:
  LLM-native structured extraction (not OCR-then-parse) plus MinIO for
  the Document intake row; fixed per-notice-type templates with LLM-filled
  slots and programmatic value substitution for the Correspondence row.
  Done directly in this commit, not left as a follow-up.
- Note under §4 ("what this costs"): §4.4 ("notices are generated, never
  sent") already covers non-delivery; add explicitly that this phase adds
  a second undelivered-artifact category — uploaded documents themselves
  are stored (§2.1) but not *managed* per the existing Object storage
  row's own caveat, now actually exercised by real Phase 3 traffic rather
  than a stated-but-unused row.

## 4. What this doc does not settle

Exact OCR/text-extraction library choice, the exact notice-template
wording/count per program (beyond "approval/denial/pending-verification"
as the three roadmap-implied types), the exact confidence-score
presentation in the worker review UI, and pgmq retry-count/visibility-
timeout tuning are Task-level implementation details, decided when that
task is actually written, not phase-level forks. Fraud Triage, Compliance/
SLA, QC, and SOP Copilot are Phase 4 — out of this doc's scope entirely,
per this project's own stated convention of a fresh design pass per phase.

The implementation plan — file-by-file, task-by-task, mirroring
`docs/plans/2026-08-23-phase-2-implementation-plan.md`'s shape — is the
next step once this doc is reviewed and approved.

## 5. AI design pattern catalog (summary)

| Pattern | Where | Why chosen |
|---|---|---|
| Transactional outbox via same-transaction `pgmq.send()` | §2.2 | pgmq's queue tables live in the same Postgres database as the operational tables, so enqueueing inside the triggering write's own transaction gets exactly the outbox-pattern guarantee a dedicated broker needs separate infrastructure to achieve. |
| LLM-native structured extraction over OCR-then-parse | §2.3 | 2026 practice favors LLM-native parsing for forms/letters/checklists — it uses layout information an OCR-then-regex pipeline discards. |
| Confidence-gated review queue, no auto-apply bypass | §2.3 | A deliberate stricter-than-industry-norm choice: confidence prioritizes review, it never skips it — the direct, literal application of "AI never owns a binding decision" to case-record writes. |
| Trusted/untrusted content boundary (extended) | §2.3 (Phase 2 §2.2) | An uploaded document is untrusted, applicant-controlled content — same boundary Phase 2 established for retrieval, applied to a documented 2026 attack surface (indirect prompt injection via document metadata/off-canvas content). |
| Bounded pipelines, not autonomous agents | §2.9 (Phase 2 §2.10) | Neither Phase 3 pipeline gives the LLM tool-calling or self-directed action — the actual mitigation for the injection risk above, not just an architectural preference. |
| Template-filling over free-form generation | §2.4 | Grounding generation in a fixed, verified structure outperforms free drafting for compliance-adjacent documents — every number/date is substituted programmatically, never LLM-generated. |
| Deterministic pre-check before human review | §2.4 (Phase 2 §2.6) | Reuses the citation-pre-check shape: a cheap, zero-noise structural/value check runs before a human (or a judge call) ever sees the draft. |
| Structured output (schema-validated) | §2.9 (Phase 2 §2.10) | Document classification output and template slot values are Pydantic-validated before use, same standard as every other AI service in this repo. |
| Single mutable status-lifecycle entity for `notice` | §2.6 | Unlike Policy Q&A's advisory-answer/binding-determination split, a notice's draft content *is* the eventual sent artifact — one row's state to track, closer to `policy_parameter_proposal`'s shape than `ai.policy_qa_answer`'s. |
| OTel `gen_ai.*` semantic conventions (extended) | §2.7 (Phase 2 §2.8) | Same instrumentation standard already adopted, extended to the worker process's own spans rather than a second observability tool. |
