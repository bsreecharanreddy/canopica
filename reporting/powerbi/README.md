# Power BI import path

Power BI Desktop is Windows-only, and this project is developed on macOS,
so the semantic model lives as TMDL text (`../semantic-model/`) rather than
a `.pbix` file, and gets imported through the Power BI **Service** instead
of authored there directly.

No `.pbix` is checked into this repo -- that's the point of the
model-as-code decision (`../semantic-model/README.md`): a binary doesn't
diff, and there's nowhere in this repo's toolchain to open one anyway.

## Import steps

1. Sign in to the [Power BI Service](https://app.powerbi.com) (a free
   account is enough for what this phase needs -- no Premium/Fabric
   capacity required).
2. Create a new workspace (or reuse an existing dev one), e.g. "IES Phase
   1a".
3. **New → Dataflow / Semantic model → Import a file**, and point it at
   `reporting/semantic-model/` -- the Service's TMDL import reads
   `ies.tmdl` and everything under `tables/` as one model.

   If your tenant's import flow doesn't support a folder of loose TMDL
   files directly, the fallback is the [Power BI Desktop project (`.pbip`)
   format](https://learn.microsoft.com/power-bi/developer/projects/projects-overview):
   copy this repo's `reporting/semantic-model/` contents into a `.pbip`
   project's own `definition/` folder structure (`ies.tmdl` as
   `model.tmdl`, `tables/*.tmdl` unchanged), then open the `.pbip` in
   Desktop on a Windows machine and publish from there. This repo doesn't
   check in a `.pbip` because nothing in this project's own toolchain can
   author or verify one.
4. When prompted for the `ServingHost` parameter, enter the serving
   Postgres host (`localhost` for `make up`'s local Compose stack; the real
   host for any other deployment).
5. Enter the `ies_serving` database credentials (`IES_METABASE_USER`-style
   local dev defaults are in `infra/.env.example`, but the semantic model
   connects directly to Postgres, not through Metabase -- use the
   `ies_app` role there instead).
6. Build a report page against the imported model's `Determinations`,
   `Eligible Rate`, and `Average Benefit` measures.

## What to check after import

- The model reads real determination data -- e.g. a card showing
  `Determinations` matches the row count the Metabase dashboard's own
  native question shows for the same filters (both read the same
  `reporting.mart_determination_outcomes` table, so they should always
  agree; a mismatch means one of them is stale, not that the two are
  allowed to differ).
- `Eligible Rate` renders as a percentage, `Average Benefit` as currency --
  both come from `formatString`s declared in the TMDL, not report-level
  formatting, so they should look right immediately on import.

## Screenshots

_Not yet captured -- requires an actual Power BI Service import, which
needs a live serving database to point at. Capture and add here once
Task 12's Compose stack (`make up`) is available to provide one; until
then this file documents the exact steps a manual walkthrough will follow._
