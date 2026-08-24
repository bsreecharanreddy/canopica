# Canopica — Analytics Copilot: which engine executes, and what actually backstops it

## 1. Why this exists

Phase 2 Task 4 builds the MetricFlow semantic layer. Writing the first
line of `semantic_models.yml` forced a question the plan and Phase 2
design doc §2.4 both assumed away, because nobody had looked at where the
gold marts physically live:

- **dbt builds silver/gold into DuckDB** (`warehouse/canopica.duckdb`, profile
  `canopica_warehouse`, adapter `dbt-duckdb`).
- **`materialize.py` then copies** the five gold marts into Postgres
  `canopica_serving.reporting.*`, which is what Metabase and the TMDL/Power BI
  model read.
- **MetricFlow binds semantic models to dbt models via `ref()`**, and dbt
  only knows the DuckDB relations. So `mf query` naturally executes
  against DuckDB.

§2.4 places `canopica_analytics_ro` — a Postgres role — underneath the
Analytics Copilot as a "defense-in-depth backstop." On the DuckDB path
that role is not on the copilot's query path at all. DuckDB is an
in-process file with no role system, so the sentence would be describing
a database the copilot never touches.

**What is settled and is not being reopened** (STATUS.md decisions table,
§2.4): authorization is resolved at MCP tool-exposure time, before any
query compiles, and that is the *primary* gate. This doc only settles
which engine executes and what the second layer actually is.

## 2. Checked against current practice

Per `canopica-ai-design-review`, this was checked by live research rather than
drafted from memory, because it touches an AI capability's security
model. Two things came back that changed the answer, and one that
confirmed it.

**Confirmed — compile-time governance is the 2026 standard, and is the
right primary gate.** The pattern this project already committed to
(resolve the caller's permitted metrics/dimensions *before* compiling)
is what the current generation of governed semantic layers does:
unauthorized intent fails compilation and data is never read, rather than
a query-time check that can only catch a violation after the fact
([Cube, *Semantic Layer for AI Agents
(2026)*](https://cube.dev/articles/semantic-layer-for-ai-agents-2026);
[Colrows, *MCP Semantic
Layer*](https://colrows.com/blogs/mcp-semantic-layer-integration/)).
Nothing to change.

**Changed (1) — "no role system" is the wrong frame; file-based engines
have their own layer.** Current guidance for keeping AI database access
genuinely read-only is four *independent* layers — scope gates, SQL
validation, session-level enforcement, and **file-level protections** —
with the explicit point that "a gap in one layer does not become an
incident." File-level protection is named as the layer that applies to
file-based databases (SQLite is the worked example: `mode=ro`,
`immutable=1`, and binding-level read-only, all three redundantly)
([Limerence, *Defense in Depth: Keeping Read-Only Really
Read-Only*](https://limerence.sh/blog/defense-in-depth-keeping-read-only-really-read-only)).
So the honest statement is not "DuckDB has no backstop." It is "DuckDB's
backstop is a different mechanism, and this project has to actually
apply it."

**Changed (2) — and this one is the reason the doc exists.** Verified
locally against this project's own DuckDB version rather than assumed:

| Probe | Result |
|---|---|
| `read_only=True`, then `INSERT` / `CREATE TABLE` / `DROP` / `ATTACH` | all blocked |
| `read_only=True`, then `select * from read_csv('/some/other/path.csv')` | **succeeded** |
| `read_only=True` **+ `SET enable_external_access=false`**, same read | blocked (`PermissionException`) |
| OS file mode `0444`, opened read-write | blocked (`IOException`) |

**A read-only DuckDB connection can still read arbitrary files off the
host filesystem.** `read_only=True` prevents *writes*; it does nothing
about `read_csv`/`read_parquet` against any path the process can reach,
or against remote URLs. This is an attack surface a Postgres role simply
does not have, and it is invisible unless someone checks — the naive
reading of "read-only connection" is that it is the safe option, and for
this specific risk it is not.

That matters here beyond theory: the operational database this project
runs alongside contains real PII-shaped data and a `pii_token` vault, and
DuckDB's own `postgres` extension is already installed and used by
`materialize.py`. An unconstrained DuckDB session is a more capable thing
than it looks.

## 3. Options

### Option A — MetricFlow on DuckDB, with the file-based layer actually applied

Semantic models live in the dbt project beside the marts they describe.
`ref()`, `mf validate-configs` and `mf query` all work against the
existing profile with no new adapter. Compatibility already checked:
`dbt-metricflow` 0.14.0 requires `dbt-core<1.13,>=1.11` and
`metricflow==0.212.0`; this project has 1.12.3 and 0.212.0 exactly, so
this adds a CLI wrapper rather than a dependency resolution.

The copilot's execution layer becomes, mapped onto the four-layer model
above:

| Layer | This system |
|---|---|
| Scope gate | MCP tool exposure — the caller's role determines which metric/dimension tools exist at all. Already settled; primary gate. |
| SQL validation | Not applicable in the usual sense, and stronger than it: **MetricFlow compiles the SQL, the LLM never writes it.** There is no LLM-authored string to validate. |
| Session enforcement | DuckDB connection opened `read_only=True` **and** `SET enable_external_access=false` — the second is the one the probe above proves is load-bearing. |
| File protection | The copilot's own read handle on `canopica.duckdb`; OS-level read-only where the deployment allows it. |

`canopica_analytics_ro` still gets created, but honestly labelled: it guards
the **Postgres serving layer** that Metabase and Power BI read. That is a
real least-privilege boundary for a real consumer — it is simply not the
copilot's boundary.

- **For:** the semantic layer sits where it belongs, next to the models
  it describes; no second adapter, target, or duplicated marts; the
  execution-layer story becomes *more* specific and more defensible than
  the original sentence, and is backed by a probe rather than an
  assumption.
- **Against:** §2.4 needs amending, and "the AI copilot's data access is
  guarded by a database role" is a slightly easier sentence to say than
  the accurate one.

### Option B — MetricFlow on Postgres `canopica_serving`

Keeps §2.4 literally true. Costs: add `dbt-postgres`, add a second dbt
target, and reconcile naming — dbt resolves `ref('mart_x')` to
`<schema>_gold.mart_x`, while `materialize.py` writes `reporting.mart_x`.
So either that Phase 1a code changes its target schema, or dbt builds
gold into Postgres directly and the marts then exist in two stores with
`materialize.py` half-redundant.

- **For:** one sentence in an existing doc stays unedited; the backstop
  is a familiar `GRANT`.
- **Against:** bends the pipeline's shape to preserve a sentence written
  before anyone checked where the data lived. It also does not remove the
  DuckDB risk from §2's probe — it relocates the copilot away from it
  while `materialize.py` keeps using DuckDB's Postgres extension anyway.

### Option C — dbt builds gold into Postgres as the primary path

The "proper" version of B. Rejected as out of scope: it re-architects a
working Phase 1a pipeline to answer a Phase 2 question, and the
motivation is still the sentence rather than a defect.

## 4. Recommendation

**Option A**, plus the three concrete controls in its table, plus a §2.4
amendment saying what `canopica_analytics_ro` actually guards.

The deciding argument is that Option A produces a *more* accurate and
more defensible security story, not a weaker one. The original sentence
claimed a backstop that would not have been on the query path; Option A
replaces it with three mechanisms that are, one of which
(`enable_external_access=false`) closes a real hole that neither the
original design nor an intuitive reading of "read-only" would have
caught.

Option B's appeal is that it makes an already-written sentence true. That
is the wrong direction of fit — the doc should describe the system.

## 5. Consequences if adopted

- Task 4 adds `dbt-metricflow` (with the `dbt-duckdb` extra) to
  `data-platform/pyproject.toml`; no adapter change.
- `semantic_models.yml` / `metrics.yml` live under
  `data-platform/dbt/canopica_warehouse/models/semantic/`, binding via
  `ref()` to the five existing gold marts.
- `canopica_analytics_ro` is still added to
  `infra/postgres/init/01-databases.sql` — with two corrections to the
  plan's own SQL, found while reading the code: the marts land in schema
  **`reporting`**, not `public`, and they are created by
  `materialize.py` running as `canopica_app`, so the `alter default
  privileges` statement must name that schema.
- Task 5 opens its DuckDB connection `read_only=True` **and** issues
  `SET enable_external_access=false`, and a test asserts the second one —
  an assertion that fails today, since a plain read-only connection reads
  arbitrary files.
- Phase 2 design doc §2.4's authorization paragraph is amended rather
  than left to contradict the implementation.

## 6. Pattern catalog

| Pattern | Where used | Why |
|---|---|---|
| Compile-time authorization | MCP tool exposure resolves the caller's metric list before any query compiles | Current standard for governed semantic layers; a violation fails compilation instead of being caught after data is read |
| No LLM-authored SQL | MetricFlow compiles every query; the LLM only selects tool names | Removes the entire "validate the model's SQL" layer rather than mitigating it, and makes hallucinated metrics fail manifest validation |
| Least privilege, engine-appropriate | DuckDB `read_only` + `enable_external_access=false` + file permissions for the copilot; `canopica_analytics_ro` for the Postgres serving layer | The mechanism has to match the engine — a role grant is meaningless for an in-process file, and a read-only file handle is meaningless for a shared server |
| Verify the control, don't assume it | The probe table in §2 | "Read-only" did not mean what it appeared to mean; the gap was only visible by testing it |
