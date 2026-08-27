# Canopica — UI Modernization: Direction Change to Stitch's Modern SaaS Language

Status: approved
Date: 2026-08-27
Supersedes: `2026-08-27-ui-modernization-public-ledger.md`'s visual-language
decisions only (§3 palette/typography/layout, §11 addendum's component
treatment). That doc is kept as-is, not rewritten, per this project's
record-not-rewrite convention — it documents a direction that was tried,
approved, and implemented across 6 real commits before being reconsidered.

## Why

The Public Ledger direction (warm paper, DM Serif Display, restrained
"stacked record sheets, not card mosaics") was implemented across Tasks
1–6 and reviewed live against the running app. The user's assessment,
direct: it reads as flat and under-polished rather than restrained —
"amateur," not "civic-editorial." Two causes were identified together:
real under-execution (the design doc's own two-column canvas+rail layout
for `CaseDetailPage`/`RuleAuthoringPage` was never built; no elevation
despite `card`/`popover` tokens existing for it; no motion despite
`framer-motion` being installed) — but also the direction itself: a
deliberately flat, paper-like aesthetic is a real, defensible choice, but
it is not what "2026-era, fluid, crisp, mature" reads as to this user.
Given a direct choice between fixing execution within Public Ledger or
changing direction, the user chose to change direction, anchored
explicitly on the Stitch mockups already reviewed (§11 of the superseded
doc) as the concrete quality bar.

## What changes

**Visual language**: adopt Stitch's actual generated system, read directly
from its rendered HTML (not just its prose spec, which drifts from what
actually rendered) — extracted from `03-case-review-audit-trail.html`'s
embedded Tailwind config and inline overrides:

- **Background**: `#F8FAFC` (Slate 50), not warm paper.
- **Surfaces**: elevated white cards (`#FFFFFF`) with a `1px solid
  #E2E8F0` (Slate 200) border and a real shadow (`shadow-sm`/`shadow-md`
  depending on elevation level) — not `RecordSheet`'s flat top-border
  accent.
- **Text**: near-black `#1b1b1d` on-surface, pure `#000000` primary for
  brand/high-authority actions (buttons, active nav).
- **Typography**: Inter throughout — body *and* headings. No serif
  display face; Stitch's own "display" role is still Inter, just larger
  and bolder (36px/700). Courier Prime stays for mono/technical data
  (trace values, hashes) — same role DM Sans's mono role served, just a
  different family already present in Stitch's own type scale.
- **AI-content distinction**: a dedicated `ai-badge` treatment —
  `#EFF6FF` background, `#1E3A8A` text, `1px solid #BFDBFE` border (Blue
  50/900/200) — replaces `AiAdvisoryBadge`'s `--info` treatment with
  Stitch's own literal values, same purpose.
- **Deterministic-content badge**: `#E2E8F0`/`#0F172A` (Slate 200/900) —
  a new, distinct treatment for human/deterministic-owned status that
  Public Ledger's `StatusPill` tones didn't have a direct equivalent for.
- **Radius**: tight, small — `0.125rem` default, `0.25rem` (lg),
  `0.5rem` (xl) — not Public Ledger's `0.5rem` default.
- **Layout density**: two-column canvas+rail on `CaseDetailPage` and
  `RuleAuthoringPage` (design doc §6's original instruction, now actually
  built), real elevation on every card-like surface, stat tiles where
  Stitch used them (already-adopted `StatTile`, not deferred to Task 8).

**What does not change**: the Tailwind v4 + shadcn/ui technical
foundation, React/Vite/TypeScript, the page-by-page migration discipline
(one commit per page, existing tests pass unmodified, manual browser
check per page), the accessibility gate, the governing AI-advisory
principle (still enforced, just with new badge colors), and the
`CalculationMatrix`/`CustodySpine`/`DecisionBar`/`PageChrome` component
set from the prior addendum — those are re-skinned, not rebuilt, since
their logic and data contracts are already correct and already
test-covered.

## Sequencing

Same order as before: foundation (tokens, shell) first, then each of the
6 already-migrated pages gets re-skinned as its own commit, verified live
in the browser each time — not one large uncommitted rewrite. Tasks 7–8
(audit trail, dashboard) inherit the new tokens automatically once built,
no separate re-migration needed.
