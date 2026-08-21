# Synthetic applicant data — source, methodology, and honest limitations

Status: approved
Date: 2026-08-21

## 1. Why this document exists

CLAUDE.md's global constraint #8: "All applicant data is synthetic. No real individual's data,
ever." This document is what makes that claim checkable rather than asserted — the exact source
file, every variable used and why, the transformation applied, and (matching
`docs/design/policy-parameter-provenance.md`'s precedent for the SNAP policy figures) the
honest limits on what a reader can conclude from data generated this way.

## 2. Source

| | |
|---|---|
| Dataset | American Community Survey (ACS) 1-Year Public Use Microdata Sample (PUMS) |
| Vintage | 2024 |
| Geography | Wyoming (state FIPS 56) — see §5.1 for why one state, and why this one |
| Person file | `https://www2.census.gov/programs-surveys/acs/data/pums/2024/1-Year/csv_pwy.zip` |
| Household file | `https://www2.census.gov/programs-surveys/acs/data/pums/2024/1-Year/csv_hwy.zip` |
| Data dictionary | `https://www2.census.gov/programs-surveys/acs/tech_docs/pums/data_dict/PUMS_Data_Dictionary_2024.csv` |
| Retrieved | 2026-08-21 |
| Records used | 5,994 person records, 2,819 household records (housing units only — see §5.3) |

Retrieved and processed by `data-platform/src/ies_data/synthetic/fetch_pums.py`, which is
**not run at test time or build time** — the output,
`data-platform/src/ies_data/synthetic/data/acs_pums_marginals.json`, is committed, so a clone
with no network access still generates data. Re-run the script to re-derive the marginals from
a fresh download, or to point at a newer vintage.

## 3. Variables used

| PUMS variable | File | Meaning | Used for |
|---|---|---|---|
| `NP` | Household | Number of persons in household | `household_size` marginal |
| `AGEP` | Person | Age | `age_by_role` marginal, age-band lookups |
| `SEX` | Person | Sex (1=Male, 2=Female) | `sex` marginal |
| `DIS` | Person | Disability recode (1=has, 2=none) | `disability_by_age_band` marginal (see §5.4 — computed, not currently sampled) |
| `ESR` | Person | Employment status recode | `employment_by_age_band` marginal |
| `RELSHIPP` | Person | Relationship to the reference person | Maps to `household_member.relationship` (§4.1) |
| `WAGP`, `SEMP` | Person | Wages; self-employment income (past 12 months) | `earned_income_monthly_deciles` (combined, see §5.5) |
| `RETP`, `SSIP` | Person | Retirement income; SSI income (past 12 months) | `unearned_income_monthly_deciles` (combined, see §5.5) |
| `TEN` | Household | Tenure (owned/rented/occupied without rent) | `tenure` marginal |
| `GRNTP` | Household | Monthly gross rent | `rent_monthly_deciles` |
| `SMOCP` | Household | Selected monthly owner costs | `mortgage_monthly_deciles` |
| `ELEP` | Household | Monthly electricity cost | `utility_monthly_deciles` (electricity only, see §5.5) |
| `ADJINC`, `ADJHSG` | Both | Income / housing-dollar adjustment factors (6 implied decimals) | Deflates reported dollars to the survey's constant-dollar basis before any decile is computed (Census's own documented usage) |
| `PWGTP`, `WGTP` | Person, Household | Person/household survey weights | Every marginal below is a **weighted** share, not a raw record count |
| `TYPEHUGQ` | Household | Housing unit vs. group quarters | Filters to housing units only (§5.3) |

## 4. Transformation

### 4.1 Relationship mapping

`RELSHIPP` (a 19-way federal relationship code) maps onto the six values
`household_member.relationship`'s CHECK constraint allows
(`portal/src/main/resources/db/migration/V1__core_entities.sql`):

| RELSHIPP | IES relationship |
|---|---|
| 20 (reference person) | `SELF` |
| 21–24 (spouse/partner, either sex) | `SPOUSE` |
| 25–27 (biological/adopted/step child) | `CHILD` |
| 29 (parent) | `PARENT` |
| 28, 30–33, 35 (sibling, grandchild, in-law, other relative, foster child) | `OTHER_RELATIVE` |
| 34, 36 (roommate, other nonrelative) | `UNRELATED` |
| 37, 38 (group quarters population) | excluded entirely — see §5.3 |

### 4.2 Dollars to monthly, constant-dollar amounts

Every PUMS income/cost variable is an **annual** figure in **that respondent's own reporting-
period dollars**, not the survey's dollars. Census's documented correction: multiply by
`ADJINC` (income) or `ADJHSG` (housing costs), each divided by 1,000,000, before comparing
across records — then divide by 12 for a monthly figure. `fetch_pums.py` applies this
uniformly; skipping it would silently understate or overstate every dollar-denominated
marginal by whatever the adjustment factor is for that record.

### 4.3 Age bands

Three bands, not a finer Census bracket: `0_17`, `18_59`, `60_plus`. The upper bound of the
middle band is 59, not an arbitrary round number — it's SNAP's own elderly threshold
(`FactAssembler.java`: `asOf.minusYears(60)`). Reusing it here ties the generator's disability
and employment marginals to the exact age cutoff the DMN rules engine evaluates against,
instead of an unrelated demographic convention.

### 4.4 Deciles, not a fitted distribution

Income and housing-cost marginals are stored as the 9 cutpoints of the 10th through 90th
percentile — an empirical decile table, not a parametric fit (no assumed normal/lognormal
shape). The generator samples by picking one of the 10 implied buckets uniformly, then a
uniform value within that bucket's range (`distributions.py::sample_from_deciles`). The top
bucket's upper edge is **estimated**, not observed: it extends the 80th–90th percentile gap one
more interval past the 90th, since deciles alone don't say how long the real tail is. This
under- or over-states the extreme tail in either direction — a documented approximation, not a
claim about the true maximum.

## 5. Honest limitations

Stated plainly, matching this repo's own standard (see the tech-stack doc's §4, the roadmap's
§8, and `policy-parameter-provenance.md`) — an unstated compromise reads as an oversight.

**5.1 One state, not a national distribution.** Wyoming was chosen for practical reasons
(the smallest PUMS file size of any state, both to fetch and to process, and no more
representative than any other), not because IES targets it. This is a national data platform
for a state-agnostic system, but "national" ACS PUMS data means combining every state's
file — outside this repo's practical scope. Real household composition, income, and housing-
cost distributions vary substantially by state and metro area; a system generating applicant
data for a specific real deployment should use that state's own PUMS file. This is a
scale-of-effort limitation, the same category as the tech-stack doc's §4.1 (thousands of
records, not millions), not a methodology flaw.

**5.2 Marginal sampling, not joint.** Household size, each member's age/role, disability
status, employment, income, and shelter cost are each sampled from their *own* independent
PUMS-derived distribution — never from the true joint distribution real households exhibit.
Two cheap, structural constraints are enforced on top of that (exactly one `SELF`, at most one
`SPOUSE` and one `PARENT` per household) precisely because they're nearly free and prevent
obviously-broken output (three spouses); nothing more elaborate is attempted. The consequence
is real and worth naming precisely: a generated household can pair, say, a 17-year-old
household head with a 38-year-old spouse, or a household head with unusually high income
alongside a randomly-drawn expensive rent that a person with that income wouldn't realistically
have chosen — because age, income, and relationship are drawn independently, not
conditionally. This is the exact limitation the tech-stack doc's §4.9 already names for the
fairness audit that will eventually run against this data (Phase 4): "sampling marginals
independently reproduces each variable's distribution but not the full joint structure... What
the audit demonstrates is that the measurement, the threshold, and the CI gate all work and
would catch a regression — not that any model here is fair in the world."

**5.3 No homeless or institutionalized households.** `TYPEHUGQ == 1` (housing units) is
filtered explicitly, excluding PUMS's group-quarters population (`RELSHIPP` 37/38) —
correctional facilities, nursing facilities, college dorms, and, materially for SNAP, emergency
and transitional homeless shelters. This isn't a generator setting that could be flipped; it's
a structural property of which population PUMS's *housing unit* sample records at all. A real
SNAP caseload includes homeless and recently-institutionalized applicants; this generator
cannot produce that population from this source file, at all, ever. `living_arrangement`'s
`HOMELESS` and `INSTITUTION` values are consequently never generated — only `RENTS`, `OWNS`,
and `SHARED_HOUSING` (mapped from PUMS's "occupied without payment of rent" tenure code).

**5.4 Disability is computed, not yet sampled.** `disability_by_age_band` is calculated and
committed to the marginals file because Step 1 of Task 9's plan names it explicitly as one of
the marginals to derive. It is **not currently used by the generator** — Task 7's intake API
(`IntakeRequest`/`IntakePersonDto`) has no field for submitting a `disability_record` at all,
so there's nowhere for a sampled value to go. Wiring this up is real, deferred work: it needs
an intake API change (a new DTO field and controller/service support), not just a generator
change, and is out of this task's scope.

**5.5 Income and cost categories are coarser than the DMN model's full type list.** The rules
engine's `income_type` recognizes eight values (`WAGES`, `SELF_EMPLOYMENT`, `UNEMPLOYMENT`,
`SOCIAL_SECURITY`, `SSI`, `CHILD_SUPPORT`, `PENSION`, `OTHER_UNEARNED`); this generator produces
only two. `WAGP` (wages) and `SEMP` (self-employment) are summed into one
`earned_income_monthly_deciles` marginal, and every generated earned-income record is labeled
`WAGES` regardless of which PUMS source it actually reflects. `RETP` (retirement) and `SSIP`
(SSI) are likewise summed into one `unearned_income_monthly_deciles` marginal and labeled
`OTHER_UNEARNED`. `ELEP` (electricity) is the only utility cost PUMS variable used — "utility
cost" here means the electric bill specifically, not a combined gas/water/electric bundle a
real household might report. All three are deliberate scope narrowings, not oversights: PUMS
doesn't offer a finer split that maps cleanly onto some of the DMN model's categories (e.g.
`CHILD_SUPPORT` has no direct PUMS analog at all), and combining what's available was judged
better than fabricating a category the source data can't actually support.

**5.6 Sex is binary.** PUMS's `SEX` variable has exactly two values. The operational schema's
`person.sex` CHECK constraint allows `'X'` as a third option; this generator never produces it,
because there is no real distribution to sample it from. A synthetic generator that invented a
share for `'X'` would be asserting a number nothing backs.

**5.7 Names and addresses are not PUMS-derived — deliberately.** PUMS microdata carries no
names or street addresses (it's federal statistical microdata, not directory data). First
names, last names, county/city/street names are drawn from small fixed lists in `generator.py`
composed specifically to read as generic and synthetic — not as an attempt to sound like real
Wyoming places or to statistically model name distributions. ZIP codes are sampled from
Wyoming's real 5-digit ZIP range for a plausible-looking address, which carries no privacy
implication (a ZIP code is a public geographic area, not personal data) and is consistent with
using WY's own PUMS file as the demographic source.

## 6. Where this feeds

`ies_data.synthetic.generator.generate_households(count, seed=seed)` produces
`SyntheticHousehold` objects shaped like the operational schema's own normalized tables;
`.to_intake_payload()` reshapes one into the exact JSON body Task 7's
`POST /api/applications` expects. `ies_data.synthetic.loader.post_households()` submits that
payload through the real HTTP API — deliberately, not a direct database insert — so every
generated household passes exactly the bean validation a real applicant's submission does.
Task 13's end-to-end test is what actually keeps the generator's output honest against Task 7's
contract on an ongoing basis; `test_generator.py`'s own contract-shape test is the first line of
defense, not the last.
