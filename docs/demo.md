# Demo: intake → determination → audit → warehouse → dashboard

A five-minute walkthrough of Phase 1a's full walking skeleton, with exact
clicks and URLs. It runs the same path
`data-platform/tests/test_end_to_end.py` proves automatically — this doc is
that same slice, but watched with your own eyes instead of asserted in a
test.

## 0. Bring the stack up

```bash
make up
```

Wait for it to finish (a few minutes on a cold build), then open
<http://localhost:3000>.

## 1. Submit an application, as a customer

The header's "Viewing as" switch defaults to **Customer**, which lands on
the **Apply for SNAP** form (`/apply`). Fill it in with something like:

| Field | Value |
| --- | --- |
| County | Laramie County |
| Street address | 100 Main St |
| City | Cheyenne |
| State | WY |
| ZIP code | 82001 |
| Living arrangement | RENTS |
| Pays utilities separately | unchecked |

Under **Head of household**, the one required member:

| Field | Value |
| --- | --- |
| First / last name | Anything |
| Date of birth | Any adult date, e.g. `1985-04-12` |
| Income | WAGES, earned, **$1200/month**, effective today (pre-filled) |
| Expense | RENT_OR_MORTGAGE, **$700/month**, effective today (pre-filled) |

Click **Submit application**. You'll land on a confirmation screen with a
reference number — that's the new `program_request`'s id. This one API
call (`POST /api/applications`, real request, no mock) just wrote a person,
a household, a household_member, an income_record, an expense_record, an
application, and a program_request, and appended an `APPLICATION_SUBMITTED`
row to the hash-chained audit log.

## 2. Run a determination, as a worker

Flip "Viewing as" to **Worker**, click **Cases** in the nav, and find the
row with the name you just entered — it shows **Not yet determined**. Click
the name to open the case.

The **Run a determination** form is pre-filled (as-of date = today,
benefit month = the 1st of this month — the same defaults
`test_end_to_end.py` uses). Click **Run determination**.

A new panel appears at the top of **Determination history** with real
output from the DMN model: Eligible/Not eligible, the monthly benefit
amount, the reason code, which policy parameter version was in force, and
when it was decided. With the numbers above the household comes back
**Eligible, $170/month** (reason code `ELIGIBLE`, policy parameter version
`SNAP-FY2026` as of this writing) — real numbers from a real run of this
exact walkthrough, not a mocked-up example.

## 3. Read the trace

Click **DMN evaluation trace** to expand it. This lazily fetches
`GET /api/determinations/{id}/trace` and lists every decision the DMN
model evaluated — `Gross Income: 1200`, `Earned Income Deduction: 240`,
`Adjusted Income: 751`, `Total Shelter Cost: 700`, `Shelter Excess: 324.5`,
`Excess Shelter Deduction: 324.5`, `Net Income: 426.5`,
`Net Income Test: PASS`, `Computed Benefit: 170`, `Benefit Amount: 170`,
and more — plus the DMN model's SHA-256 hash and the exact policy
parameter version used. This is the full "why," persisted at
determination time, not reconstructed after the fact.

## 4. Verify the audit chain

```bash
cd data-platform
uv run python -m canopica_data.audit.verify_chain --dsn "postgresql://canopica_app:canopica_app@localhost:5432/canopica_operational"
```

Prints `audit chain: N rows checked, ok=True` — recomputes every row's hash
from the first row to the last and confirms it matches what's stored,
proving the `APPLICATION_SUBMITTED` and `DETERMINATION_MADE` events from
steps 1–2 are exactly what they claim to be, not just present.

## 5. Run the pipeline and open the dashboard

```bash
make pipeline
```

This ingests the operational tables to bronze, runs the dbt silver/gold
build, materializes the gold mart into the serving database, and
provisions Metabase — all four steps, one command. Then open
<http://localhost:3001> (sign in with `admin@canopica.local` / `CanopicaAdmin123!`
the first time) and open the **SNAP determinations** dashboard.

The table's `August 1, 2026 / ELIGIBLE / 1 / $170` row (dates will differ
by the time you run this) is the determination from step 2 — same
outcome, same benefit amount, same everything you saw in the trace panel.
That's the point of Task 11/12's "materialize, don't re-derive" design: the
number on the dashboard is a copy of the number the rules engine decided,
not a recomputation of it. (Other rows may already be on the dashboard —
from this repo's own end-to-end test, `test_end_to_end.py`, which runs the
same slice against a random benefit month each time so repeat runs don't
collide; harmless, and a good sign the test and this walkthrough are
exercising the same real code path.)

## Teardown

```bash
make down
```

Also removes the Postgres volume, so the next `make up` starts clean.
