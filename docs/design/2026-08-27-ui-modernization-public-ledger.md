# Canopica — UI Modernization: The Public Ledger Design System

Status: approved
Date: 2026-08-27
Relates: roadmap doc §3.3's Accessibility decision (carries forward
unchanged); resolves STATUS.md's "When should the UI get a dedicated
modernization pass?" open question, raised 2026-08-23.

This is a design doc, not an implementation plan. It settles the visual
direction, the technical foundation, and the scope boundary. Migration
order, exact component file layout, and task-by-task sequencing are
`docs/plans/`'s job, written from this doc.

## 1. Why this exists

`ui/`'s five real pages (`IntakePage`, `WorkerCasesPage`, `CaseDetailPage`,
`PolicyQaPage`, `RuleAuthoringPage`) and their shared components carry
zero CSS today — plain semantic HTML, no stylesheet anywhere in `src/`.
Functional, not styled. Since this is a portfolio project and the UI is
its most interviewer-visible surface, a dedicated modernization pass was
flagged as worth real resource investment (STATUS.md, 2026-08-23) — timed
to a natural break point rather than interrupting phase work. Phase 2's
Task 9 wrapping is that break point.

## 2. Source and boundary: the Manus exploration

The visual direction below originates from a design exploration done in
Manus, in a separate scratch repository
(`bsreecharanreddy/canopica-benefits-platform`), not this one. That repo
built a complete four-phase vision prototype — including Phase 3/4
screens Canopica hasn't implemented yet — on its own fake backend
(tRPC + Drizzle + Express), independent of anything in this repo.

**Boundary, decided going in and unchanged by this doc:** that repo is
design reference, not source to merge. Nothing from it is imported,
linked, or added as a dependency. Its component code (a single 135KB
`Home.tsx` driving all screens via internal view state — itself a
pattern this repo wouldn't want to copy structurally) is read for ideas,
not ported. Its own written design rationale (`ideas.md`) and its
realized CSS tokens (`index.css`, `phase34.css`) are the two artifacts
actually drawn on here — a considered visual language and the concrete
values it resolved to, re-implemented natively against this app's own
React 19/Vite 8/TypeScript stack, its existing routing and role model,
and its existing accessibility gate. This keeps the portfolio narrative
intact: this repo's commit history shows this project's own engineering
judgment applied to a design direction, not a generated app absorbed
wholesale.

## 3. The chosen direction: Public Ledger

Manus explored three directions (Public Ledger, Field Station, Signal
Grid) and converged on **Public Ledger** — contemporary civic
editorialism, a digital interpretation of public records and reporting
desks. It fits Canopica specifically: this is a system whose entire
premise is showing its work (a persisted DMN trace, a hash-chained audit
log, human reviewers of record), and the design language makes exactly
that visible rather than decorating over it.

- **Principles**: evidence before assertion (source, effective date,
  reviewer, and deterministic status shown wherever a system conclusion
  appears); calm operational clarity through typography and spacious
  columns, not dashboard density; human accountability as first-class
  information; a visible paper trail for how a case reached its current
  state.
- **Color**: a warm paper field (not stark white) as the base, deep
  ink-black for seriousness, **Canopica Verdigris `#167C6B`** reserved
  specifically for governed/affirmed states — not general-purpose brand
  color — plus a restrained amber/red/blue signal triad for
  exception/risk/informational status.
- **Typography**: DM Serif Display for case titles and high-value
  section statements; DM Sans (tabular numerals) for all operational UI,
  tables, and body text. Hierarchy comes from size and weight, not color.
- **Layout**: a "case-file desk" — a persistent dark left rail
  identifying operating context, a slim utility top bar for global
  controls, editorial columns with a dominant working canvas and a
  narrower evidence/activity rail where a page has evidence to show.
  Detail views read as stacked record sheets, not card mosaics.
- **Signature elements**: a vertical chain-of-custody spine with
  timestamp nodes; small numbered registration marks; a thin decision bar
  placing amount, policy version, and reviewer ownership side by side.
- **Interaction**: hover reveals source metadata rather than concealing
  it; filters are explicit; binding actions carry intentional
  confirmation language; AI affordances always disclose their
  advisory-only scope — the last point a direct match for this repo's own
  governing principle.
- **Motion**: brief 160–220ms transitions for panels/filters/navigation;
  record rows enter with restrained opacity transitions staggered ~35ms;
  the custody spine draws in subtly on page entry. Dollar amounts and
  determinations are never animated. All non-essential motion respects
  reduced-motion preferences.
- **Voice**: headlines state operational facts ("Every determination has
  a trace"); CTAs name the specific resulting action; microcopy states
  authority and boundaries rather than generic reassurance.

## 4. Scope for this pass

**In scope**: a real, shared design system (tokens, layout shell, core
component primitives) applied to the 5 pages that exist in real Canopica
today, against the real Java/Spring API.

**Explicitly out of scope**:

- Phase 3/4 screens (document intake, integrity triage, SOP copilot,
  policy-approval workflows). These get built from this same design
  system once those phases are real — not mocked ahead of their backend,
  which would be building UI for a system that doesn't exist yet.
- Manus's own backend scaffold (tRPC, Drizzle, Express, S3) — not
  referenced or ported in any form.
- A dark-mode toggle. Manus's shadcn scaffold includes a `.dark` theme by
  default; Public Ledger's actual direction is a light, warm-paper
  design. Not building a theme switcher solely because the scaffold
  happened to include one.
- Live/public deployment (e.g. Vercel). Separate, already-open decision
  (STATUS.md) that has to be weighed against the repo-visibility plan;
  unaffected by this doc.
- A Storybook-style component showcase page. Skippable scope under
  YAGNI — see §9.
- Any change to `App.tsx`'s routing or role logic, or to domain logic in
  existing components (`DeterminationPanel`, `TracePanel`,
  `HouseholdMemberFields`, the API client). This is a visual migration —
  logic is untouched.

## 5. Technical foundation

New dependencies: `tailwindcss` v4, `tw-animate-css`, `framer-motion`,
and shadcn/ui's Radix-based primitives — generated via the shadcn CLI
into `ui/src/components/ui/` as owned source (shadcn is a code generator,
not an npm runtime component library), matching how Manus's own reference
app is built. Fonts (DM Serif Display, DM Sans) are self-hosted via
`@fontsource` packages rather than a runtime Google Fonts request, so
page render has no new external network dependency.

Design tokens are re-derived, not imported: Manus's `index.css` still
carries shadcn's generic default blue theme (never updated to match its
own chosen direction), while the actual Public Ledger values live in
`phase34.css`'s hand-authored rules. This doc's tokens take those
resolved *values* — warm paper background, ink foreground, Verdigris
`#167C6B` as `--color-primary`, the amber/red/blue signal triad, the
DM Serif Display / DM Sans type scale — and set them as Canopica's own
CSS custom properties feeding Tailwind's `@theme`, in `ui/src/index.css`.
No Manus CSS file is imported.

## 6. Layout and component architecture

`App.tsx`'s current shell (a plain `<header>`/`<nav>`/`<main>`) becomes
the case-file desk: a persistent dark left rail carrying the Canopica
mark and role-appropriate navigation — still driven by the existing
`HOME_FOR`/role-conditional logic, restyled not rewritten — plus a slim
top utility bar for page-level context (breadcrumb, the current
case/program-request id, sign-out). Content is editorial columns: a
dominant canvas plus a narrower evidence rail on pages that have
something to put there (`CaseDetailPage`'s determination and
`TracePanel` against an audit/history rail; `RuleAuthoringPage`'s editor
against a validation rail). Simpler single-purpose pages (`IntakePage`'s
form, `PolicyQaPage`'s Q&A) stay single-column.

Foundation-task component inventory, built once and shared by all 5
pages:

- **NavRail** + **TopUtilityBar** — the shell above, role-aware
- **Button**, **Input/Select/Checkbox** (shadcn primitives) — replace
  today's bare form elements in `IntakePage`, `HouseholdMemberFields`,
  `IncomeFields`, `ExpenseFields`
- **RecordSheet** — the stacked-record-sheet container, for case rows in
  `WorkerCasesPage` and detail sections in `CaseDetailPage`
- **StatusPill** — determination/case status, program code
- **DecisionBar** — the amount/policy-version/reviewer strip, for
  `CaseDetailPage`
- **CustodySpine** — the timestamped trace line, for `TracePanel`
- **FormField** — label+input+error wrapper for intake's form-heavy
  surface

## 7. Accessibility and motion

The axe-clean/jsx-a11y gate from Phase 1b is unchanged and non-negotiable
— every migrated page keeps its `vitest-axe` assertion (already a
devDependency), run against the new markup. Radix gives correct ARIA
roles and keyboard/focus handling by default, which is a head start, not
a substitute for the check. One thing that specifically does *not*
transfer automatically: Manus's hand-picked OKLCH values were chosen for
this look, not run through a contrast checker for this app's actual
text/background pairings — WCAG AA contrast gets verified explicitly per
pairing as part of the foundation task.

Motion follows §3's spec exactly, gated behind `prefers-reduced-motion`
via Framer Motion's `useReducedMotion`. The one hard rule, carried over
from CLAUDE.md's governing principle: motion never animates a dollar
amount or anything that could read as the system computing or altering a
determination live. It decorates an already-decided, fixed value —
never the value itself.

## 8. Testing

Same tooling as today — Vitest + React Testing Library — extended with
the accessibility assertion per migrated page. No new visual-regression
tooling is introduced; not part of the current stack, and this task alone
doesn't justify adding one (YAGNI). Per CLAUDE.md's UI-change rule, each
page migration also gets a manual check against a real running dev
server in a browser before being called done — automated tests verify
correctness, not that the feature actually looks and works right.

## 9. Execution approach

Three approaches were considered:

- **Big-bang** — build the whole system and migrate all 5 pages in one
  pass. Rejected: one large, hard-to-review diff, against a testing
  policy that wants tests per unit of work, not one bundled proof at the
  end.
- **Foundation, then page-by-page (chosen)** — one task builds the
  foundation (tokens, shell, shared primitives), then each of the 5 pages
  is migrated as its own task: its own commit, its own tests, in
  dependency order. Matches CLAUDE.md's one-commit-per-step convention
  directly.
- **Component showcase first** — same as above, plus a Storybook-style
  showcase page before touching real pages. Adds a step that isn't
  earning its keep here: the 5 real pages are the actual proof this
  system works, and Manus already produced one showcase pattern that
  isn't being carried over (§4). Not built.

Exact page migration order is deliberately left to the implementation
plan, not fixed here.

## 10. Recording

Per this project's design-decision workflow:

- **Roadmap doc §3.3** gains one row: UI design system choice (Public
  Ledger direction, Tailwind + shadcn/ui foundation), pointing here.
- **STATUS.md**: the "When should the UI get a dedicated modernization
  pass?" open question (2026-08-23) moves to "Decisions already made,"
  rewritten to reflect that it's now scheduled and designed, pointing
  here.
- **No tradeoffs-doc entry.** The tradeoffs doc tracks substitutions for
  what a real production system would use, with a fidelity mark and, for
  genuine compromises, a stated cost. Tailwind + shadcn/ui isn't a
  scaled-down stand-in for something a real deployment would do
  differently — it's a legitimate, common production choice in its own
  right, the same category of decision as picking React itself. Nothing
  here is a compromise to disclose.
