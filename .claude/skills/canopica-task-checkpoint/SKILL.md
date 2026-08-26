---
name: canopica-task-checkpoint
description: Use when completing one task from a Canopica implementation plan (docs/plans/*.md) — the per-task regression gate CLAUDE.md's non-negotiable testing policy requires before calling a task done.
---

# Canopica task checkpoint

CLAUDE.md's testing policy is explicit: "No implementation code gets
committed without tests, and the full suite runs before every push. Not
the tests for the area that changed — the whole suite, every time." This
skill is that gate, run once per completed task.

## 1. Run the full suite, not a scoped subset

    make test
    make lint

Both must be clean. `make test` runs every layer (Java Testcontainers,
Python pytest, web Vitest) — a task that only touched `rules-engine/`
still runs `api/`'s, `ui/`'s, and `data-platform/`'s tests too. The point is
catching a regression in earlier-phase work, not just verifying the new
code.

## 2. Report the actual result

State which tests ran and how many, matching the granularity every prior
STATUS.md verification-log row already uses (e.g. "Java: +4 tests over
Task 5 ... Python: 2 integration tests against a real Postgres instance").
If anything failed, say so plainly — CLAUDE.md requires the actual result,
failures included, not an assumption of success.

## 3. Update docs/STATUS.md in the same commit

Add a row to the Verification log table (date, task/scope, exact commands,
result), and flip the task's row in the Phase 1a/1b table to "Done" with
its commit hash once known. Not a follow-up step: CLAUDE.md states a
STATUS.md update done separately "drifts and stops being trustworthy."

## 4. Did this task change what the README diagram depicts?

If the task added, removed, or renamed a component, or changed a
data/control flow shown in the README's "Architecture, at a glance"
Mermaid diagram, update that diagram in the same commit too — CLAUDE.md's
Conventions section states this explicitly, same reasoning as the
STATUS.md rule above: a diagram nobody keeps current actively misleads a
reader instead of just being silent. Most tasks won't touch this; check
before assuming it doesn't apply.

## 5. Did a call site start touching a new external dependency?

**This is the one check that has failed three separate times in this
repo, always the same way, always caught only after a red CI run.** Not a
hypothetical — the three incidents, all in `docs/STATUS.md`'s
verification log:

| Task | Code started needing | Which job lacked it |
|---|---|---|
| 5 | `data-platform`'s built `mf`/`dbt` binaries | `ai`, `e2e-ai` never ran its `uv sync` |
| 7 | Postgres (`answer_general` writes provenance) | `ai-eval` brings up only opensearch+ollama |
| 8 | Jaeger (the new OTel tracer exports spans) | `ai-eval`, same reason |

The shape is identical every time: a call site quietly grows a new
external dependency, and **the CI jobs that execute that call site are a
different set than the ones you were thinking about**. Local `make test`
can't catch it — locally every service is already up from `make up`, and
one `uv sync` per project persists across the whole session.

So, mechanically, before pushing:

1. **Did this task's diff add a network/subprocess/filesystem call to
   anything outside its own project?** A new client, a new exporter, a
   new `subprocess` call, a new DSN/URL/port read from config. If no,
   skip the rest.
2. **Which CI jobs execute that call site?** Grep `.github/workflows/ci.yml`
   for every job that runs the entry point reaching it. Remember the
   non-obvious ones: `ai-eval` runs `run_eval.py` directly, *not* through
   pytest, so no test fixture or monkeypatch protects it — it exercises
   the real production path with nothing stubbed.
3. **For each such job, confirm it either provisions the dependency or
   explicitly opts out.** Opting out is often the better answer: a job's
   wall-clock budget is a real constraint (see `ai-eval`'s own timing
   comments), so a settings flag that degrades gracefully beats standing
   up another container. Task 7 opted out with
   `record_provenance=False`, Task 8 with `CANOPICA_OTEL_ENABLED=false` — both
   turned out to be the *correct* production behavior too, not just a CI
   workaround.

The failure mode when you skip this is never a clean error. Task 8's was
dozens of silent multi-second retry stalls; Task 7's was a
`connection refused` only reachable once an earlier bug stopped masking
it. Both cost a full red-CI round trip to find something this grep
would have caught in seconds.

## 6. One commit for the task, then push — every time, no exception

Task code + its tests + the STATUS.md update (+ the diagram update, if
step 4 applied, + the CI-job change, if step 5 applied) land together,
not as a bundle of several unrelated commits. If a task genuinely splits into sub-steps (e.g. a schema
migration commit, then a service commit), each one still gets its own
STATUS.md verification-log row for what it actually verified — don't
defer all of it to a final combined entry.

**Then `git push` to origin/main immediately — don't stop at a local
commit and wait to be asked.** A commit that isn't pushed doesn't exist
as far as GitHub, CI, or a reader of the repo is concerned; leaving it
local is the same failure mode this whole skill exists to prevent for
tests and STATUS.md.

## 7. New dependency, schema choice, or stack substitution this task made?

That's a design decision, not just an implementation detail — use the
`canopica-design-decision` skill to record it (STATUS.md's decisions table,
and the tradeoffs doc if it substitutes for a real production choice)
instead of leaving it implicit in the diff.
