# Canopica semantic model (TMDL)

`canopica.tmdl` and `tables/mart_determination_outcomes.tmdl` are the semantic
model authored as text -- TMDL (Tabular Model Definition Language),
Microsoft's model-as-code format for Power BI/Analysis Services. It's
authored here rather than as a Power BI Desktop `.pbix` binary because
Power BI Desktop is Windows-only and this project is developed on macOS;
model-as-code also means the model reviews and diffs like any other file in
this repo, instead of being an opaque binary (the risk the Phase 1
vertical-slice design doc's §12 flagged and this decision resolves).

## What's declared

One table, `mart_determination_outcomes`, mirroring the gold mart's own
contract (`data-platform/dbt/canopica_warehouse/models/gold/gold.yml`) column
for column -- `test_semantic_model.py` in `data-platform/tests/` enforces
that the two never drift apart.

Three measures:

- **Determinations** -- `SUM(determination_count)` in the current filter
  context.
- **Eligible Rate** -- eligible determinations divided by all
  determinations, in the current filter context.
- **Average Benefit** -- `DIVIDE(SUM(total_benefit_amount),
  SUM(determination_count))`, a determination-count-weighted average.
  Deliberately not `AVERAGE(average_benefit_amount)`: the mart's grain is
  already one row per (month, program, outcome, reason, parameter version)
  group, and naively averaging those per-group averages would weight every
  group equally regardless of how many determinations it actually
  represents -- wrong the moment group sizes differ.

## Importing into Power BI

See `../powerbi/README.md` for the exact import steps (Power BI Service,
since Desktop isn't available on this development machine) and screenshots.

## Connecting to a different serving host

The model's `ServingHost` parameter (declared in `canopica.tmdl`) defaults to
`localhost` for local development. Power BI's own parameter UI (or the
Service's dataset settings, post-import) is where this gets pointed at a
real deployment's serving Postgres host -- no TMDL edit needed for that.

## Drafting new measures/visuals with the dashboard-authoring copilot

`ai/src/canopica_ai/dashboard_assist` (Phase 2 Task 6) drafts new DAX measures
and report visuals from a natural-language request, grounded in the real
tables/columns/measures above -- it never invents a reference that doesn't
already exist here, and it never writes into `canopica.tmdl` or `tables/`.

```sh
cd ai && uv run python -m canopica_ai.dashboard_assist.cli propose \
    --prompt "add a measure for the average benefit per eligible determination"
```

This writes a timestamped `.tmdl`-formatted proposal file under
`proposals/`. Review it like any other diff, then hand-apply the accepted
parts into the real TMDL files above (or script the merge via Tabular
Editor's CLI) -- the existing publish step (see "Importing into Power BI"
above) is unchanged and still the only path anything reaches a live
report through.
