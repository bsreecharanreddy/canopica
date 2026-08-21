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
still runs `portal/`'s and `data-platform/`'s tests too. The point is
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

## 4. One commit for the task

Task code + its tests + the STATUS.md update land together, not as a
bundle of several unrelated commits. If a task genuinely splits into
sub-steps (e.g. a schema migration commit, then a service commit), each
one still gets its own STATUS.md verification-log row for what it actually
verified — don't defer all of it to a final combined entry.

## 5. New dependency, schema choice, or stack substitution this task made?

That's a design decision, not just an implementation detail — use the
`canopica-design-decision` skill to record it (STATUS.md's decisions table,
and the tradeoffs doc if it substitutes for a real production choice)
instead of leaving it implicit in the diff.
