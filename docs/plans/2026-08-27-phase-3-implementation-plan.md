# Phase 3 — Case Intake & Communication AI: Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.
> Execute tasks in order, one commit per completed task, `docs/STATUS.md`
> updated in that same commit (CLAUDE.md, "Conventions"). Run the
> `canopica-task-checkpoint` skill's gate (`make test`, `make lint`, STATUS.md,
> one commit) after every task. Push at natural task-cluster boundaries
> (roughly every 2-4 tasks, or whenever a task's correctness genuinely
> depends on CI-only conditions this repo can't fully verify locally),
> not after every single commit and not held to the end of the phase —
> Actions minutes are a metered, finite resource this project has already
> hit real limits against.

**Goal:** Stand up Phase 3's case-intake and communication AI on top of
Phase 1's operational system: Intelligent Document Intake
(classify/extract/route, worker-confirmed, no exceptions), AI-drafted
correspondence (template-filled, validation-gated, human-approved), and
translation/localization — plus the infrastructure neither of the first
two can exist without: object storage, `pgmq`, and this repo's first
async worker process.

**Spec:** `docs/design/2026-08-21-full-system-and-phased-roadmap.md` §3.2/
§3.3/§3.4/§5 (what), `docs/design/2026-08-27-phase-3-case-intake-
communication-ai-design.md` (how — read this one first, it resolves every
open question this plan assumes as settled), `docs/design/2026-08-21-tech-
stack-and-production-tradeoffs.md` (fidelity/cost rationale for every
substitution below).

**Starting point, worth internalizing before Task 1:** confirmed against
the actual repo state while writing the design doc — none of the
following exist yet: an object store, the `pgmq` extension, any
background-worker process, a `NOTICE`/`document` table, or a UI
translation library. Every earlier phase's async-sounding language
("worker" in `docs/demo.md`) refers to a human caseworker role, not a
background job processor — determinations run synchronously today. Phase
3 is the first place this codebase does anything asynchronously at all.

---

## Global constraints

Everything Phase 1a's, Phase 1b's, and Phase 2's plans stated still
applies (never name a real agency; full suite before every push;
synthetic data only; AI never makes a binding decision; structured
output at every AI→system boundary). Phase 3 adds:

16. **No confidence-based bypass of human review, anywhere in this
    phase.** Document Intake's per-field confidence score prioritizes the
    review queue; it never skips the worker-confirm step, at any score.
    Correspondence's deterministic pre-check runs before a human sees a
    draft; it never substitutes for the human approval step. If a task's
    own design would let either pipeline write to a case record or send a
    notice without an explicit human action, that is a design bug — stop
    and revise the task.
17. **Every `pgmq.send()` call happens inside the same `@Transactional`
    boundary as the write it's about** (design doc §2.2) — a `document`
    insert, an `eligibility_determination` commit. This is what makes the
    enqueue transactionally safe; an enqueue call outside that boundary
    silently gives up the guarantee the whole design leans on.
18. **Uploaded documents are untrusted content**, same threat-model
    boundary as applicant-submitted free text (roadmap §3.3, Phase 2
    design doc §2.2) — nothing extracted from a document is treated as a
    trusted instruction, and the mitigation for that is architectural
    (no tool-calling, no autonomous action in either pipeline), not a
    content filter.

### New dependencies this phase

| Component | Choice | Why |
|---|---|---|
| Object storage | MinIO (`minio/minio`) | Design doc §2.1; tradeoffs doc's Object storage row (tier-level decision, first actually stood up here) |
| Postgres w/ `pgmq` | An image bundling the `pgmq` extension, replacing plain `postgres:16-alpine` | Design doc §2.2; exact image tag pinned at Task 1 |
| Worker language/framework | Python, `worker/` (new `uv`-managed project, sibling to `ai/`/`data-platform/`) | CLAUDE.md language policy; design doc §2.2 |
| OCR/text extraction | A maintained open-source OCR/PDF-text-extraction library, exact package pinned at Task 3 | Design doc §2.3, §2.8 ("pin at implementation time") |
| UI i18n | `react-i18next` | Design doc §2.5 |
| PDF rendering (notices) | A maintained open-source HTML/text-to-PDF library, exact package pinned at Task 6 | Design doc §2.4, tradeoffs doc's Correspondence row |

### Prerequisites before Task 1

- [ ] Docker Desktop running with real memory headroom — this session's
      own local verification work found the Docker Desktop VM's default
      allocation (7.65GB observed) insufficient once OpenSearch's `-Xmx3g`
      heap, Ollama, and the full dev stack (api/keycloak/postgres/jaeger)
      all run together; MinIO and pgmq's Postgres add further to that.
      Confirm headroom or stop non-essential services before running the
      full local stack for this phase's own verification.
- [ ] Confirm the exact `pgmq`-bundled Postgres image at Task 1 time
      against what's current and maintained then, not assumed here.

---

## File structure (additions only)

```
canopica/
  worker/
    pyproject.toml                          <- Task 1
    uv.lock                                 <- Task 1
    src/canopica_worker/
      __init__.py
      config.py                             <- Task 1
      queue.py                              <- Task 1 (pgmq read/delete/archive wrapper)
      document_intake_consumer.py           <- Task 3
      correspondence_consumer.py            <- Task 5
      main.py                               <- Task 1 (entrypoint, polls both queues)
    tests/
      conftest.py                           <- Task 1
      test_queue.py                         <- Task 1
      test_document_intake_consumer.py      <- Task 3
      test_correspondence_consumer.py       <- Task 5
  ai/src/canopica_ai/
    document_intake/
      schema.py                             <- Task 3 (Pydantic extraction schema)
      classify.py                           <- Task 3
      service.py                            <- Task 3
    correspondence/
      templates/                            <- Task 5 (per notice_type template files)
      schema.py                             <- Task 5
      draft.py                              <- Task 5
      validate.py                           <- Task 5
      service.py                            <- Task 5
  ai/tests/
    test_document_intake.py                 <- Task 3
    test_correspondence.py                  <- Task 5
  api/src/main/resources/db/migration/
    V17__document.sql                       <- Task 2
    V18__notice.sql                         <- Task 5
    V19__audit_event_types_phase3.sql       <- Task 2/5 (widen CHECK constraint)
  api/src/main/java/canopica/api/
    document/Document.java, DocumentRepository.java, DocumentService.java  <- Task 2
    api/DocumentController.java             <- Task 2 (upload), Task 4 (review/confirm)
    notice/Notice.java, NoticeRepository.java, NoticeService.java          <- Task 5
    api/NoticeController.java               <- Task 6 (review/approve/reject)
  ui/src/
    pages/DocumentReviewPage.tsx            <- Task 4
    pages/NoticeReviewPage.tsx              <- Task 6
    i18n/                                   <- Task 7 (react-i18next config + locale files)
  infra/
    docker-compose.yml                      <- modified: +minio, postgres image swap, Task 1
  .github/workflows/ci.yml                  <- modified: +worker job, +minio/pgmq to relevant integration jobs
  Makefile                                  <- modified: worker lint/test targets folded into make test/lint
```

---

## Task list

| # | Task | Deliverable |
|---|---|---|
| 1 | Object storage, pgmq & worker scaffold | MinIO + pgmq-enabled Postgres in compose; `worker/` project polls two empty queues end to end |
| 2 | Document upload & storage | `document` table; authenticated upload endpoint stores to MinIO, enqueues `document_intake` in the same transaction |
| 3 | Document classification & extraction | Worker consumes `document_intake`; LLM structured extraction against a Pydantic schema with per-field confidence |
| 4 | Document review UI | Caseworker reviews/confirms extracted fields; confirmed values flow into the real intake tables through existing paths |
| 5 | Correspondence drafting | `notice` table; worker consumes `correspondence_dispatch`; template-filled draft + deterministic pre-check |
| 6 | Notice review, approval & dispatch | Worker/admin reviews a draft, approves or rejects; PDF rendering; `SENT` status recorded |
| 7 | Translation/localization | UI i18n live for the 7 real pages; correspondence translation routed through the same §5/§6 gate |
| 8 | Observability & Phase 3 wrap-up | `gen_ai.*` spans on worker pipelines; pgmq queue-depth/archive Grafana panel; full-suite verification |

---

## Task 1: Object storage, pgmq & worker scaffold

Stands up every piece of new infrastructure this phase depends on before
any feature code is written against it: MinIO, a `pgmq`-enabled Postgres,
and `worker/` itself as a real, runnable (if empty) consumer of two named
queues. No document/notice logic yet — this task proves the plumbing.

**Files:**
- Create: `worker/pyproject.toml`, `worker/uv.lock`
- Create: `worker/src/canopica_worker/__init__.py`, `config.py`, `queue.py`, `main.py`
- Create: `worker/tests/conftest.py`, `test_queue.py`
- Modify: `infra/docker-compose.yml` (+`minio`; swap `postgres` image to a
  `pgmq`-bundled tag; a one-shot init step creating the `document_intake`
  and `correspondence_dispatch` queues via `pgmq.create()`)
- Modify: `Makefile`, `.github/workflows/ci.yml` (+`worker` job, same
  shape as the existing `ai` job)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `canopica_worker.queue.read(queue_name, visibility_timeout) ->
  Message | None`, `.delete(queue_name, msg_id)`, `.archive(queue_name,
  msg_id)` — thin wrappers over pgmq's own `pgmq.read`/`pgmq.delete`/
  `pgmq.archive` SQL functions, the only interface `document_intake_
  consumer.py` (Task 3) and `correspondence_consumer.py` (Task 5) use;
  neither talks to pgmq's SQL functions directly.
- Consumes: the operational Postgres directly (`psycopg`, already this
  repo's driver of choice per `data-platform`'s own dependency set).

- [ ] **Step 1: `worker/` project scaffold.** `uv init` at `worker/`,
      package `canopica_worker`; `pyproject.toml` mirrors `ai/pyproject.
      toml`'s `[tool.ruff]`/`[tool.mypy]` blocks (`strict = true`, target
      py312). Add to `Makefile`'s `test`/`lint` targets and a new
      `worker` job in `ci.yml`.
- [ ] **Step 2: Postgres image swap.** Replace `postgres:16-alpine` with
      the pinned `pgmq`-bundled image; confirm every existing migration
      and test still passes unchanged (a pure base-image swap should be
      invisible to everything that isn't pgmq-specific — if it isn't,
      that's a real finding to record, not silently work around).
- [ ] **Step 3: MinIO service.** `minio` in compose, one bucket
      (`canopica-documents`) created via a one-shot init step (`mc mb`,
      same "init container" shape `ollama-init` already uses in this
      compose file), local-dev credentials via the same environment-
      variable pattern every other service already uses.
- [ ] **Step 4: Queues.** A one-shot init step (or `worker/`'s own
      startup code, idempotent either way) runs `pgmq.create('document_
      intake')` and `pgmq.create('correspondence_dispatch')`.
- [ ] **Step 5: `queue.py` + `main.py`.** The read/delete/archive
      wrapper, and an entrypoint that polls both queues (empty for now —
      Tasks 3/5 add real consumers) with the visibility-timeout/retry-
      then-archive behavior design doc §2.2 specifies.
- [ ] **Step 6: Tests.** `test_queue.py`: send a message, read it back,
      confirm it's invisible to a second read before the visibility
      timeout and visible again after; delete removes it for good; a
      message that exceeds the retry limit lands in pgmq's archive, not
      lost.
- [ ] **Step 7: Full suite + commit.**

---

## Task 2: Document upload & storage

**Files:**
- Create: `api/src/main/resources/db/migration/V17__document.sql`
- Create: `api/src/main/java/canopica/api/document/Document.java`,
  `DocumentRepository.java`, `DocumentService.java`
- Create: `api/src/main/java/canopica/api/api/DocumentController.java`
  (upload endpoint only this task; review/confirm endpoints are Task 4)
- Create: `api/src/main/resources/db/migration/V19__audit_event_types_
  phase3.sql` (widen `AuditEventType`'s CHECK constraint — done once here
  for both this task's `DOCUMENT_UPLOADED`/`DOCUMENT_CLASSIFIED` and Task
  5's `NOTICE_*` events, same "widen once" pattern V16 already used for
  Phase 2's single new event type)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `POST /api/cases/{programRequestId}/documents` (multipart
  upload, worker- or citizen-authenticated per the existing dual-
  filter-chain pattern — caseload-scoped via the existing
  `CaseAssignmentService.checkCaseloadAccess` for the worker path).
  Stores the object to MinIO (Task 1's bucket), inserts a `document` row,
  and calls `pgmq.send('document_intake', ...)` inside the same
  transaction (constraint 17 above) — all three happen or none do.

- [ ] **Step 1: `document` table.** Per design doc §2.6: `id`,
      `program_request_id`, `object_key`, `content_type`, `uploaded_by`,
      `uploaded_at`, `classification_status` (`PENDING`/`CLASSIFIED`/
      `CONFIRMED`/`REJECTED`).
- [ ] **Step 2: Object key derivation.** Derived from `program_request_
      id` and a generated document id only — never from the uploaded
      filename (design doc §2.1's stated reason: an applicant-controlled
      filename must not be able to traverse or collide).
- [ ] **Step 3: Upload endpoint + transactional enqueue.** Stores to
      MinIO, inserts the `document` row, calls `AuditService.append`
      (`DOCUMENT_UPLOADED`), and `pgmq.send` — all inside one
      `@Transactional` method.
- [ ] **Step 4: Tests.** Upload succeeds and the object is retrievable
      from MinIO; the `document` row and the pgmq message both exist
      after a successful upload; a simulated failure partway through
      (e.g. the DB insert failing) leaves neither the MinIO object
      referenced by a row nor a queued message for a nonexistent
      document — the transaction boundary actually holds.
- [ ] **Step 5: Full suite + commit.**

---

## Task 3: Document classification & extraction

**Files:**
- Create: `ai/src/canopica_ai/document_intake/schema.py`, `classify.py`,
  `service.py`
- Create: `ai/tests/test_document_intake.py`
- Create: `worker/src/canopica_worker/document_intake_consumer.py`
- Create: `worker/tests/test_document_intake_consumer.py`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `canopica_ai.document_intake.service.classify_and_extract(
  object_key: str, content_type: str) -> DocumentExtraction`, a Pydantic
  model carrying `document_type`, a list of extracted `fields` (name,
  value, `confidence: float`), and `matched_verification_ids: list[UUID]`
  (which of the program request's outstanding `verification` rows this
  document appears to satisfy). This is the sole interface the worker
  consumer calls; it never talks to the LLM directly.
- Consumes: MinIO (fetches the object by key), the local OCR/text-
  extraction library for scanned uploads, Ollama for the LLM extraction
  call itself (same client `ai/common/llm_client.py` already provides).

- [ ] **Step 1: Extraction schema.** Pydantic model per document type
      (income report, renewal packet, work activity report,
      verification-checklist document) per design doc §2.3's list —
      fields specific to each type, plus the shared `confidence` per
      field.
- [ ] **Step 2: OCR fallback for scanned uploads.** `classify.py` checks
      content type; image-only uploads get the OCR/text-extraction pass
      first, feeding extracted text (plus page images, if the LLM client
      supports multimodal input) into the same extraction step as a
      native-text document.
- [ ] **Step 3: LLM structured extraction.** One call, schema-validated
      response (same `response_format`/schema pattern Phase 2's services
      already use), against Ollama by default.
- [ ] **Step 4: Verification matching.** Compares the extraction's
      `document_type` and content against the `program_request`'s
      outstanding `verification` rows (fetched via a read-only call the
      worker makes back to the API, or a direct read of the same
      Postgres — decide which at implementation time, consistent with
      how Task 5's determination-record reads work) to propose which
      checklist item(s) this document satisfies.
- [ ] **Step 5: Worker consumer.** `document_intake_consumer.py` reads a
      message, fetches the `document` row, calls `service.
      classify_and_extract`, writes the result somewhere the review UI
      (Task 4) can read (a new column or small table on `document` —
      decide the exact shape at implementation time), sets
      `classification_status = 'CLASSIFIED'`, appends `DOCUMENT_
      CLASSIFIED` to the audit log, then deletes the message. A
      processing failure leaves the message for pgmq's own retry/
      visibility-timeout behavior (Task 1), never a silent drop.
- [ ] **Step 6: Guardrail note, not new code** (design doc §2.3): confirm
      in review/tests that a document's extracted content never reaches
      anything beyond the structured schema and the review UI — no
      tool-calling, no path back into case data before Task 4's human
      confirmation.
- [ ] **Step 7: Tests.** `test_document_intake.py`: each document type
      extracts its expected fields from a synthetic fixture document;
      a low-quality/ambiguous fixture produces a low confidence score,
      not a confident wrong answer papered over. `test_document_intake_
      consumer.py`: a queued message is processed end to end against a
      real local MinIO+Postgres+Ollama stack, `classification_status`
      transitions correctly, and a processing exception leaves the
      message for retry rather than crashing the consumer loop.
- [ ] **Step 8: Full suite + commit.**

---

## Task 4: Document review UI

**Files:**
- Modify: `api/src/main/java/canopica/api/api/DocumentController.java`
  (+review-queue list endpoint, +confirm endpoint)
- Modify: `api/src/main/java/canopica/api/document/DocumentService.java`
  (confirm applies confirmed field values through the *existing* intake-
  record write paths — never a new direct-write path)
- Create: `ui/src/pages/DocumentReviewPage.tsx`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `GET /api/cases/documents/review-queue` (caseload-scoped,
  ordered by confidence ascending so the lowest-confidence extractions
  surface first — design doc §2.3's "confidence drives prioritization");
  `POST /api/cases/documents/{documentId}/confirm` (worker-edited or
  worker-accepted field values; on confirm, writes through the same
  paths a caseworker's manual entry already uses — `IncomeRecordRepository
  .save()`, `VerificationService`'s existing status-update path, etc. —
  never a new write path bypassing them).

- [ ] **Step 1: Review-queue endpoint.** Caseload-scoped (reuses
      `CaseAssignmentService.checkCaseloadAccess`, same pattern as every
      other worker-facing case endpoint), returns `CLASSIFIED` documents
      with their extracted fields and confidence scores.
- [ ] **Step 2: Confirm endpoint.** Accepts the worker's final field
      values (pre-filled from the extraction, editable) — this is the
      literal human-confirmation gate design doc §2.3 requires with no
      bypass. On confirm: applies values through existing write paths,
      sets `classification_status = 'CONFIRMED'`, appends `DOCUMENT_
      CLASSIFIED`'s sibling confirmation event to the audit log (reuse
      `VERIFICATION_UPDATED` where the confirm satisfies a verification,
      per §2.3's matching step).
- [ ] **Step 3: `DocumentReviewPage.tsx`.** Lists the caseload's review
      queue (lowest confidence first), per-field confidence display
      (visual emphasis on low-confidence fields per design doc §2.3), an
      editable confirm form. Follows the existing Public Ledger
      component set (`PageChrome`, etc.) — no new visual language.
- [ ] **Step 4: Accessibility pass** (this project's standing bar for
      every UI page, Phase 1b onward): confidence indicators are not
      color-only; form fields keyboard-navigable; confirm action has a
      clear focus state.
- [ ] **Step 5: Tests.** Java: review-queue endpoint is caseload-scoped
      (a worker not holding the assignment gets a 403, same test shape
      as `WorkerCaseControllerTest`'s existing audit-trail test); confirm
      applies values through the real existing write path and the
      resulting `income_record`/`verification` row is exactly what a
      manual caseworker entry would have produced. Vitest/RTL: the page
      renders the queue, an edit-then-confirm flow calls the confirm
      endpoint with the edited values, not the original extraction.
- [ ] **Step 6: Live manual check** (this project's UI convention): run
      the real local stack, upload a real fixture document, watch it
      reach the review queue, confirm it, verify the resulting case data.
- [ ] **Step 7: Full suite + commit.**

---

## Task 5: Correspondence drafting

**Files:**
- Create: `api/src/main/resources/db/migration/V18__notice.sql`
- Create: `api/src/main/java/canopica/api/notice/Notice.java`,
  `NoticeRepository.java`, `NoticeService.java`
- Modify: `api/src/main/java/canopica/api/determination/...` (wherever
  the determination-commit transaction lives — the `pgmq.send` for
  `correspondence_dispatch` is added here, inside that same transaction,
  per constraint 17)
- Create: `ai/src/canopica_ai/correspondence/templates/` (per
  `notice_type` template files: approval, denial, pending-verification),
  `schema.py`, `draft.py`, `validate.py`, `service.py`
- Create: `ai/tests/test_correspondence.py`
- Create: `worker/src/canopica_worker/correspondence_consumer.py`
- Create: `worker/tests/test_correspondence_consumer.py`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `canopica_ai.correspondence.service.draft(determination_id:
  UUID) -> NoticeDraft` (Pydantic: `notice_type`, filled `content`,
  `template_version`, `validation_result`). The worker consumer is the
  only caller.
- Consumes: the `eligibility_determination`/`determination_trace`
  records (read-only) and the audit trail, matching design doc §2.4's
  "the LLM composes explanation of numbers that are already correct."

- [ ] **Step 1: `notice` table.** Per design doc §2.6: single table,
      status lifecycle (`DRAFT`/`APPROVED`/`REJECTED`/`SENT`), AI
      provenance columns directly on it (prompt version, generation
      model, generation params), `validation_result` jsonb.
- [ ] **Step 2: Transactional enqueue on determination commit.**
      `pgmq.send('correspondence_dispatch', {determination_id})` added
      inside the existing determination-commit transaction — drafting
      never holds up the binding decision (constraint 17; roadmap §Phase
      3).
- [ ] **Step 3: Notice templates.** One template per `notice_type`
      (approval, denial, pending-verification) with named slots; every
      dollar amount/date slot is filled by *programmatic substitution*
      from the determination record, not by the LLM (design doc §2.4's
      central mechanism decision) — the LLM's own job is limited to the
      plain-language explanation slots.
- [ ] **Step 4: `draft.py`.** Fills the explanation slots from the
      determination trace + audit trail via one LLM call, schema-
      validated against `schema.py`'s Pydantic model.
- [ ] **Step 5: `validate.py`.** The deterministic pre-check (design doc
      §2.4): every required slot filled; every number/date the filled
      template asserts matches the determination record's own value by
      exact comparison — not LLM-judged. Runs before the draft is ever
      persisted as reviewable.
- [ ] **Step 6: Worker consumer.** `correspondence_consumer.py` reads a
      message, calls `service.draft`, inserts the `notice` row (status
      `DRAFT`, `validation_result` populated), appends `NOTICE_DRAFTED`
      to the audit log, deletes the message. A validation failure still
      produces a `DRAFT` row (with the failing `validation_result`
      recorded) rather than silently retrying forever — a human reviewer
      needs to see *why* it failed, same as any other draft.
- [ ] **Step 7: Tests.** `test_correspondence.py`: each `notice_type`'s
      template fills correctly from a synthetic determination fixture;
      a deliberately-wrong LLM output (mismatched dollar amount) is
      caught by the deterministic pre-check, not silently accepted.
      `test_correspondence_consumer.py`: end to end against a real local
      stack, a determination commit results in a `DRAFT` notice row with
      correct content.
- [ ] **Step 8: Full suite + commit.**

---

## Task 6: Notice review, approval & dispatch

**Files:**
- Create: `api/src/main/java/canopica/api/api/NoticeController.java`
- Modify: `api/src/main/java/canopica/api/notice/NoticeService.java`
  (approve/reject/dispatch)
- Create: `ui/src/pages/NoticeReviewPage.tsx`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Produces: `GET /api/cases/notices/review-queue`, `POST /api/cases/
  notices/{noticeId}/approve`, `POST /api/cases/notices/{noticeId}/
  reject`. Approve renders the approved content to PDF (the pinned
  library from Task 1's dependency table), sets `status = 'SENT'`
  (design doc's "dispatch" — generated, never actually delivered, per
  the tradeoffs doc's unrevisited §4.4), stamps `sent_at`, appends
  `NOTICE_APPROVED` then `NOTICE_SENT` to the audit log.

- [ ] **Step 1: Review-queue + approve/reject endpoints.** Caseload-
      scoped, same pattern as Task 4's document review queue.
- [ ] **Step 2: PDF rendering on approve.** No path renders/marks-sent
      without the explicit approve action — no auto-send, matching
      design doc §2.4 exactly.
- [ ] **Step 3: `NoticeReviewPage.tsx`.** Shows the filled draft, the
      deterministic pre-check's own result (a failed check is visibly
      flagged, not hidden), approve/reject actions. Same component set
      as every other page.
- [ ] **Step 4: Accessibility pass.**
- [ ] **Step 5: Tests.** Java: approve/reject endpoints caseload-scoped;
      approve produces a real PDF and the correct audit events in order;
      reject leaves `status = 'REJECTED'` with no PDF and no `SENT`
      event. Vitest/RTL: a failed pre-check renders visibly; approve and
      reject both call the right endpoint.
- [ ] **Step 6: Live manual check.**
- [ ] **Step 7: Full suite + commit.**

---

## Task 7: Translation/localization

**Files:**
- Create: `ui/src/i18n/` (react-i18next config, locale files for the 7
  real pages that exist by this point in the phase)
- Modify: `ai/src/canopica_ai/correspondence/service.py` (+translation
  path, same validation/review gate as §5/§6, per design doc §2.5)
- Modify: `docs/STATUS.md`

- [ ] **Step 1: UI i18n.** `react-i18next` wired in; English plus at
      least one additional locale's translation file for every existing
      page's static copy. Pure tooling, no LLM involved (design doc
      §2.5) — this step alone touches no AI code.
- [ ] **Step 2: Correspondence translation.** A translated draft is
      generated through the *same* `draft.py`/`validate.py` path Task 5
      built, parameterized by target language — never a separate,
      less-reviewed code path. The deterministic number/date check
      (Step 5 of Task 5) still applies unchanged.
- [ ] **Step 3: Tests.** UI: a locale switch actually changes rendered
      copy on at least one page (Vitest/RTL). `ai/`: a translated notice
      draft for a fixture determination passes the same deterministic
      pre-check as the English draft, and a deliberately-mistranslated
      dollar amount is caught the same way an English one would be.
- [ ] **Step 4: Full suite + commit.**

---

## Task 8: Observability & Phase 3 wrap-up

**Files:**
- Modify: `worker/src/canopica_worker/*` (+`gen_ai.*` spans around each
  classify/draft LLM call, +spans around each `pgmq.read`/`delete`/
  `archive` cycle — same OTel stack Phase 1b/2 already built, no new tool,
  per design doc §2.7)
- Modify: Grafana provisioning (a new panel: queue depth + archive rate
  for both `document_intake` and `correspondence_dispatch`)
- Modify: `docs/STATUS.md` (Phase 3 definition-of-done verification)

- [ ] **Step 1: Worker spans.** `gen_ai.*` conventions on the LLM calls
      inside `classify_and_extract`/`draft`; a plain span around each
      queue read/delete/archive cycle with the queue name and message
      age as attributes.
- [ ] **Step 2: Grafana panel.** Queue depth (pgmq's own visibility
      view) and archive-table row count for both queues, so a stuck
      consumer or a repeatedly-failing message is visible operationally.
- [ ] **Step 3: End-to-end verification.** A real document upload →
      classification → confirm → case-data-updated path, and a real
      determination → draft → approve → `SENT` path, both run against
      the live local stack, not mocked — same "verified for real" bar
      Phase 1a's `docs/demo.md` and Phase 1a/1b/2's `pytest -m e2e` suites
      already hold this project to.
- [ ] **Step 4: Full suite, push, CI-confirm.**

---

## Phase 3 definition of done

- [ ] All 8 tasks committed, each with its own green full-suite run.
- [ ] Every task's CI job (`worker`, plus `ai`/`api`/`ui`'s existing jobs
      extended to cover new code) is CI-confirmed green — not just
      locally verified, per this project's established "CI-confirmed"
      bar (`docs/STATUS.md`'s own verification-log language throughout
      Phase 1b/2).
- [ ] A live, manual walkthrough of both pipelines end to end (Task 8's
      Step 3) is run for real before this phase is called done, same
      discipline `docs/demo.md` already set for Phase 1a.
- [ ] `docs/STATUS.md` reflects Phase 3 as done, at the same task
      granularity Phase 1b/2 already use.
- [ ] The README's architecture diagram updates to show `worker/`, MinIO,
      and pgmq — per CLAUDE.md's same-commit convention for that diagram.

## Deferred out of Phase 3, on purpose

Fraud Risk Triage, the SLA/Compliance Monitor, the QC Assistant, the SOP
Copilot, and SOP Process-Improvement Mining are Phase 4 — out of this
plan's scope entirely, per this project's own stated convention of a
fresh design pass per phase. A structured feedback loop on notice-draft
rejections feeding future template refinement, and OCR confidence fusion
across multiple extraction passes, are both noted in the design doc §2.9
as considered-but-deferred — real, but additive scope, not needed given
this phase's every-extraction-gets-reviewed posture.
