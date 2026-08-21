# IES rules engine

DMN decision tables for SNAP eligibility, evaluated via Drools/KIE
(`kie-dmn`), plus a thin pure-Java library around them. No Spring, no
database, no clock of its own — `SnapFacts` and `SnapPolicyParameters` are
already resolved by the caller (the portal's `FactAssembler` and
`PolicyParameterResolver`) before this module ever runs. That is what makes
every rule table-driven testable in isolation and what makes an evaluation
reproducible years later: replaying the exact same two inputs against this
same model always produces the exact same `SnapDecision`.

## The numbers-vs-logic boundary

- **Numbers** (thresholds, rates, household-size lookups) live in the
  database, effective-dated, resolved as of a decision date, and never
  touched by this module.
- **Logic** (test ordering, exemptions, deduction stacking, the benefit
  formula) lives entirely in `src/main/resources/dmn/snap-eligibility.dmn`.

If a change is "the FY2026 numbers came out," it's a new
`policy_parameter_set` row in the portal, not a change here. If a change is
"SNAP started applying deductions in a different order," it's a change to
this DMN model.

## The decision graph

Fifteen named decisions, each individually named so each one lands in the
persisted `DETERMINATION_TRACE` — a worker (or a future reader) can see the
deduction stack step by step, not just the final answer.

| # | Decision | Kind | Logic |
|---|---|---|---|
| 1 | `Gross Income` | literal | `Facts.earnedIncome + Facts.unearnedIncome` |
| 2 | `Gross Test Exempt` | literal | `Facts.hasElderlyOrDisabledMember or Facts.categoricallyEligible` |
| 3 | `Gross Income Within Limit` | literal | `Gross Income <= Parameters.grossIncomeLimit` |
| 4 | `Gross Income Test` | decision table (UNIQUE) | exempt → `"EXEMPT"`; within limit → `"PASS"`; else `"FAIL"` |
| 5 | `Earned Income Deduction` | literal | `Facts.earnedIncome * Parameters.earnedIncomeDeductionRate` |
| 6 | `Dependent Care Deduction` | literal | `Facts.dependentCareCost` |
| 7 | `Medical Expense Deduction` | decision table (UNIQUE) | elderly/disabled → `max(0, medicalExpense - threshold)`; else `0` |
| 8 | `Adjusted Income` | literal | gross minus standard/earned/dependent-care/medical deductions, floored at 0 |
| 9 | `Total Shelter Cost` | literal | `Facts.shelterCost + Facts.utilityCost` |
| 10 | `Shelter Excess` | literal | shelter cost above 50% of adjusted income, floored at 0 |
| 11 | `Excess Shelter Deduction` | decision table (UNIQUE) | elderly/disabled → uncapped; else capped at `Parameters.excessShelterCap` |
| 12 | `Net Income` | literal | adjusted income minus the shelter deduction, floored at 0 |
| 13 | `Net Income Test` | decision table (UNIQUE) | categorically eligible → `"EXEMPT"`; within net limit → `"PASS"`; else `"FAIL"` |
| 14a | `Computed Benefit` | literal | `max(0, maxAllotment - ceiling(netIncome * benefitReductionRate))` |
| 14 | `Benefit Amount` | decision table (FIRST) | fail either test → `0`; positive computed benefit → that amount; zero/negative and household size ≤ the minimum-benefit cutoff → the minimum benefit; else `0` |
| 15 | `Determination` | context | `{ eligible, benefitAmount, reasonCode }` |

`reasonCode` is one of `ELIGIBLE`, `GROSS_INCOME_EXCEEDS_LIMIT`,
`NET_INCOME_EXCEEDS_LIMIT`, `ZERO_BENEFIT_AMOUNT` — the last one is what
distinguishes a household whose *computed* benefit rounds to zero (a real
denial) from one that gets the statutory minimum benefit instead. A
three-or-more-person household whose computed benefit is zero is a denial,
not a $0 award (see decision 14, row 4's household-size guard).

## Deliberately out of scope for Phase 1a

Named here so nobody mistakes an absence for an oversight: the asset/
resource test, the child-support-paid deduction, the homeless shelter
deduction, state-level utility allowance variation, and ABAWD work
requirements. Each is a decision to add to this same model later, not a
redesign — the numbers-vs-logic split holds regardless of how many more
decisions get added.

## Testing

`SnapDmnEvaluatorTest` is table-driven: one test per SNAP scenario (gross-
income pass/fail, net-income pass/fail, each deduction applied in the
correct order, categorical eligibility, the minimum-benefit floor, and the
"computes to zero is a denial" case), plus one proving the as-of-date
correctness CLAUDE.md's testing policy requires — the same facts under two
different parameter versions must produce different benefits, proving the
parameters are genuinely injected rather than baked into the model.
`DmnModelSanityTest` runs first and exists specifically because the
`kie-dmn` bootstrap and FEEL name resolution can't be verified just by
reading the XML — a model-authoring mistake fails there, not confusingly
inside a scenario test.
