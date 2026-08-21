# SNAP Policy Parameter Provenance

Every figure seeded into `policy_parameter_set`/`policy_parameter` by
`V4__seed_snap_parameters.sql` (Task 3 of the Phase 1a plan) is transcribed
from a published USDA Food and Nutrition Service (FNS) document, for the
48 contiguous states and the District of Columbia only (this repo does not
model Alaska/Hawaii/Guam/Virgin Islands COLA variants — see the Phase 1a
plan's "deferred, on purpose" list). Retrieved and verified 2026-08-21.

Two figures — the earned-income deduction rate, the medical expense
deduction threshold, the benefit-reduction rate, the shelter-income share,
and the minimum-benefit household-size cutoff — are set by statute/
regulation, not by the annual COLA, and do not change year to year. They
are cited separately below rather than to a COLA memo, since no COLA memo
states them.

## FY2025 (effective 2024-10-01 through 2025-09-30)

**Sources:**
- "Supplemental Nutrition Assistance Program (SNAP) Fiscal Year (FY) 2025
  Maximum Allotments and Deductions," USDA FNS, updated 10/1/2024.
  <https://fns-prod.azureedge.us/sites/default/files/media/file/FY2025-Maximum-Allotments-Deductions.pdf>
- "Supplemental Nutrition Assistance Program (SNAP) Fiscal Year (FY) 2025
  Income Eligibility Standards," USDA FNS, updated 10/1/2024.
  <https://fns-prod.azureedge.us/sites/default/files/media/file/FY2025-Income-Eligibility-Standards.pdf>
- Minimum benefit ($23) is not stated in either PDF above; corroborated via
  Louisiana DCFS's public FY2025 SNAP COLA summary (which cites the same
  FNS figures): "the minimum monthly allotment remains $23."
  <https://dcfs.louisiana.gov/news/snap-income-thresholds-deductions-and-resource-limits-increase-october-1/>

| Parameter | HH size | Value |
|---|---|---|
| `MAX_ALLOTMENT` | 1 / 2 / 3 / 4 | 292 / 536 / 768 / 975 |
| `MAX_ALLOTMENT` | 5 / 6 / 7 / 8 | 1158 / 1390 / 1536 / 1756 |
| `MAX_ALLOTMENT` | each additional | +220 (not seeded — sizes 1-8 only, see Phase 1a plan) |
| `STANDARD_DEDUCTION` | 1-3 / 4 / 5 / 6+ | 204 / 217 / 254 / 291 |
| `GROSS_INCOME_LIMIT` (130% FPL) | 1 / 2 / 3 / 4 | 1632 / 2215 / 2798 / 3380 |
| `GROSS_INCOME_LIMIT` | 5 / 6 / 7 / 8 | 3963 / 4546 / 5129 / 5712 |
| `NET_INCOME_LIMIT` (100% FPL) | 1 / 2 / 3 / 4 | 1255 / 1704 / 2152 / 2600 |
| `NET_INCOME_LIMIT` | 5 / 6 / 7 / 8 | 3049 / 3497 / 3945 / 4394 |
| `EXCESS_SHELTER_CAP` | — | 712 |
| `MINIMUM_BENEFIT` | — | 23 |

## FY2026 (effective 2025-10-01, open-ended)

**Source:** "SNAP – Fiscal Year 2026 Cost-of-Living Adjustments," memo dated
2025-08-13, signed Ronald Ward, Acting Associate Administrator, SNAP, USDA
FNS, addressed "TO: All State Agencies." A single memo with attached
tables (this is the primary COLA memo itself, not a per-table extract).
<https://www.usda.gov/sites/default/files/guidance-documents/fns.snap-cola-fy26memo.pdf>

| Parameter | HH size | Value |
|---|---|---|
| `MAX_ALLOTMENT` | 1 / 2 / 3 / 4 | 298 / 546 / 785 / 994 |
| `MAX_ALLOTMENT` | 5 / 6 / 7 / 8 | 1183 / 1421 / 1571 / 1789 |
| `STANDARD_DEDUCTION` | 1-3 / 4 / 5 / 6+ | 209 / 223 / 261 / 299 |
| `GROSS_INCOME_LIMIT` (130% FPL) | 1 / 2 / 3 / 4 | 1696 / 2292 / 2888 / 3483 |
| `GROSS_INCOME_LIMIT` | 5 / 6 / 7 / 8 | 4079 / 4675 / 5271 / 5867 |
| `NET_INCOME_LIMIT` (100% FPL) | 1 / 2 / 3 / 4 | 1305 / 1763 / 2221 / 2680 |
| `NET_INCOME_LIMIT` | 5 / 6 / 7 / 8 | 3138 / 3596 / 4055 / 4513 |
| `EXCESS_SHELTER_CAP` | — | 744 |
| `MINIMUM_BENEFIT` | — | 24 |

## Statutory/regulatory (not COLA-adjusted; same both fiscal years)

**Sources:** 7 U.S.C. § 2014(e) (deductions), 7 U.S.C. § 2017(a) (benefit
computation), 7 CFR § 273.9(d) (deductions), 7 CFR § 273.10(e) (benefit
levels).

| Parameter | Value | Basis |
|---|---|---|
| `EARNED_INCOME_DEDUCTION_RATE` | 0.20 | 7 U.S.C. § 2014(e)(2); 7 CFR 273.9(d)(2) |
| `MEDICAL_EXPENSE_THRESHOLD` | 35 | 7 U.S.C. § 2014(e)(5); 7 CFR 273.9(d)(3) — only the portion of a qualifying elderly/disabled member's medical expense above this monthly threshold is deductible |
| `SHELTER_INCOME_SHARE` | 0.50 | 7 CFR 273.9(d)(6)(ii) — shelter costs count as "excess" only above 50% of income after other deductions |
| `BENEFIT_REDUCTION_RATE` | 0.30 | 7 U.S.C. § 2017(a); 7 CFR 273.10(e)(2)(ii)(F) — the statutory 30%-of-net-income benefit formula |
| `MINIMUM_BENEFIT_MAX_HOUSEHOLD_SIZE` | 2 | 7 CFR 273.10(e)(2)(iii) — the minimum benefit applies only to 1- and 2-person households |

## Known limitation stated once, here

Only the 48-states-and-DC column is modeled. Real SNAP COLA figures also
vary by Alaska (three sub-regions), Hawaii, Guam, and the U.S. Virgin
Islands — out of scope per the roadmap's stated 48-states-and-DC framing
(`docs/design/2026-08-20-phase1-vertical-slice.md` §2) and not revisited
here.
