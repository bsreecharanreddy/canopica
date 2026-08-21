---
name: canopica-design-decision
description: Use when a new Canopica architecture or tooling choice needs deciding or recording — a new dependency, a stack substitution, or an open "should we do X" question — before any code for a new subsystem gets written.
---

# Canopica design decision

CLAUDE.md: "Every design decision goes through brainstorm → dated doc in
docs/design/ → user approval → implementation plan, before any code gets
written. Don't skip straight to code on a new subsystem." This skill is
that workflow, plus exactly where a settled decision gets recorded.

## 1. Check docs/STATUS.md's "Decisions already made" table first

Don't relitigate something already settled there. If the question is
answered, cite it instead of reopening it.

## 2. Brainstorm the tradeoff before proposing a fix

For an open question, give a short recommendation and the main tradeoff —
not an exhaustive survey — and let the user redirect before anything gets
written down as settled.

## 3. Once approved, record it in all three places that matter

Recorded once here so a fresh session doesn't reopen it — this is the
exact shape the pgmq decision took (commit 683747a):

- **Roadmap doc** (`docs/design/2026-08-21-full-system-and-phased-roadmap.md`)
  §3.3's cross-cutting decisions table — the choice and its one-line
  rationale.
- **Tradeoffs doc**
  (`docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`) — if
  the decision substitutes for what a real production system would use,
  add a row to the right tier table with a fidelity mark (`=` identical,
  `≈` same-shape, `~` substituted). If it's a genuine compromise (not just
  a same-shape swap), add a numbered entry to §4 stating what it actually
  costs — an unstated compromise reads as an oversight. A zero-cost
  substitution also gets added to §5's list.
- **`docs/STATUS.md`**'s "Decisions already made" table — one row, pointing
  at where the full reasoning lives.

## 4. Don't write implementation code yet

A recorded decision is not an implementation plan. If it unlocks new work,
that work still needs its own entry in a `docs/plans/` file before code
gets written, per CLAUDE.md's phase-plan convention.
