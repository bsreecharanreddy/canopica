# Phase 1a — Walking Skeleton: Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.
> Execute tasks in order, one commit per completed task, `docs/STATUS.md`
> updated in that same commit (CLAUDE.md, "Conventions").

**Goal:** Build the thinnest path that touches every layer of Canopica and
produces a real, correct, auditable, reproducible SNAP eligibility
determination — intake through determination, audit chain, warehouse, and a
report page — demoable with one command.

**Architecture:** A Spring Boot API owns the operational Postgres store and
embeds a Drools/KIE DMN runtime. Policy *numbers* live in an effective-dated
`policy_parameter_set` table and are resolved as of a decision date; policy
*logic* lives in versioned DMN decision tables. Every determination persists
a full evaluation trace and appends to a hash-chained audit log the database
itself refuses to mutate. A Python ingestion job lands operational tables as
Delta Lake bronze; dbt-duckdb builds silver dimensions/facts and one gold
mart; the mart is materialized into a serving Postgres database that
Metabase (and a TMDL semantic model for Power BI) reads.

**Tech stack:** Java 17 · Spring Boot 3.5.3 · Drools/KIE `kie-dmn` 10.2.0 ·
Postgres 16 · Flyway 11 · Testcontainers 1.21 · React 19 + Vite + TypeScript
+ Vitest · Python 3.12 (uv) · Pydantic v2 · Polars · DuckDB · dbt-duckdb ·
deltalake · Metabase · Docker Compose · GitHub Actions.

**Spec:** `docs/design/2026-08-21-full-system-and-phased-roadmap.md`
(authoritative), with `docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`
for stack rationale and `docs/design/2026-08-20-phase1-vertical-slice.md`
for background (superseded on four points — see its header).

---

## Global constraints

Every task's requirements implicitly include all of these.

1. **Never name a real agency, a real state benefits program instance, or a
   consulting firm/systems integrator** in code, docs, test fixtures, seed
   data, or commit messages. The system is called Canopica. Technology vendor
   names (Drools, Metabase, Power BI, Azure…) are fine and expected.
   *(CLAUDE.md, "What this project is")*
2. **AI drafts, deterministic systems decide.** No LLM appears anywhere in
   Phase 1a. Every number in this phase is computed by DMN or SQL.
3. **No implementation code is committed without tests, and the full suite
   runs before every push** — the whole suite, not just the changed area.
   *(CLAUDE.md, "Testing policy")*
4. **One commit per completed task**, carrying its own code, its own tests,
   its own green full-suite run, and its own `docs/STATUS.md` update in the
   same commit.
5. **Python-first where the language is open** — data platform, generator,
   tooling. `uv`, Pydantic v2, `ruff`, `mypy --strict`, `pytest`, Polars.
   Java/Spring stays for the portal API and the DMN evaluation only.
6. **Effective dating is not optional.** Every intake entity carries
   `effective_from` / `effective_to`; every determination stores the
   `policy_parameter_set` version it used, never a pointer to "current".
   *(Roadmap §3.5)*
7. **`ELIGIBILITY_DETERMINATION` is append-only.** A changed circumstance
   produces a new determination row; nothing mutates an existing one.
8. **All applicant data is synthetic.** No real individual's data, ever.
9. **Local-first:** the whole stack runs with no cloud account, no API key,
   and no trial credential.

### Versions pinned for this phase

| Thing | Version | Note |
|---|---|---|
| Java | 17 | `/opt/homebrew/opt/openjdk@17` — the only JDK installed here |
| Maven | 3.9.16 | Installed 2026-08-21; committed wrapper `./mvnw` is what CI uses |
| Spring Boot | 3.5.3 | Parent POM |
| Drools/KIE `kie-dmn-core` | 10.2.0 | Requires Java 17+ |
| Flyway | 11.8.2 | `flyway-core` + `flyway-database-postgresql` |
| Testcontainers | 1.21.3 | Requires a running Docker daemon |
| Postgres | 16 | Container image `postgres:16-alpine` |
| Node | 26.4.0 / npm 11.17.0 | Installed |
| Python | 3.12 | **Not** the system 3.14 — dbt-core support lags new Python releases; `uv` pins 3.12 per project |

### Prerequisites before Task 1

- [ ] **Docker Desktop is running.** `docker info` must succeed —
      Testcontainers (Task 2 onward), Metabase, and the Compose stack all
      need it. Docker Desktop is installed at `/Applications/Docker.app` but
      was not running as of 2026-08-21; the `docker compose` v2 subcommand
      appears once it starts (the `/usr/local/bin/docker-compose` v1 binary
      on this machine is legacy — do not use it).
- [ ] **`uv` installed:** `brew install uv`.

---

## File structure

Directories follow the roadmap's §6 layout exactly. Nothing outside these
paths is created in Phase 1a.

```
canopica/
  pom.xml                                  <- Maven aggregator (portal, rules-engine)
  mvnw, mvnw.cmd, .mvn/wrapper/            <- committed Maven wrapper; CI uses ./mvnw
  Makefile                                 <- one-liner entry points (make up / test / e2e)
  .editorconfig .gitignore .gitattributes

  rules-engine/                            <- DMN tables + a pure evaluation library
    pom.xml
    src/main/resources/dmn/snap-eligibility.dmn
    src/main/java/canopica/rules/
      SnapFacts.java                       <- immutable input record
      SnapPolicyParameters.java            <- immutable resolved-parameter record
      SnapDecision.java                    <- immutable output record (+ trace map)
      DmnEvaluationException.java
      SnapDmnEvaluator.java                <- wraps kie-dmn DMNRuntime; no Spring, no DB
    src/test/java/canopica/rules/
      SnapDmnEvaluatorTest.java            <- table-driven scenarios
      DmnModelSanityTest.java              <- model loads, no DMN compilation messages

  portal/                                  <- Spring Boot API + React app
    pom.xml
    src/main/resources/db/migration/       <- Flyway: V1__…V6__
    src/main/java/canopica/portal/
      CanopicaPortalApplication.java
      domain/                              <- JPA entities
      repo/                                <- Spring Data repositories
      policy/PolicyParameterResolver.java
      determination/DeterminationService.java
      audit/AuditService.java
      intake/IntakeService.java
      api/                                 <- REST controllers + DTOs
      config/                              <- role stubs, JSON config
    src/test/java/canopica/portal/…
    web/                                   <- React app (Vite, TS)
      package.json vite.config.ts tsconfig.json
      src/api/client.ts src/pages/ src/components/ src/test/

  data-platform/
    pyproject.toml uv.lock
    src/canopica_data/
      config.py
      synthetic/                           <- ACS PUMS-driven generator
      ingestion/                           <- Postgres -> Delta bronze
      serving/                             <- gold -> serving Postgres
      audit/verify_chain.py                <- CI chain verifier
      reporting/provision_metabase.py
    dbt/canopica_warehouse/                     <- dbt-duckdb project
      dbt_project.yml profiles.yml models/{bronze,silver,gold}/ macros/ tests/
    tests/                                 <- pytest (unit + integration + e2e)

  reporting/
    semantic-model/                        <- TMDL model-as-code
    dashboard/                             <- Metabase provisioning assets + README
    powerbi/README.md                      <- import instructions (no .pbix binary)

  infra/
    docker-compose.yml
    postgres/init/                         <- role creation for operational + serving DBs
    .env.example

  .github/workflows/ci.yml
```

**Responsibility boundaries worth stating once:**

- `rules-engine/` has **no Spring, no database, no Jackson-to-DB coupling**.
  It takes facts + already-resolved parameters and returns a decision plus a
  trace. That is what makes it unit-testable table-driven and portable.
- **Numbers live in `policy_parameter_set` (database, effective-dated,
  immutable); logic lives in DMN (versioned in git).** Household-size
  lookups are a *number* and resolve in `PolicyParameterResolver` before the
  DMN call. Test ordering, exemptions, deduction stacking, and the benefit
  formula are *logic* and live in the DMN model. Every task below respects
  this line.
- The hash chain is computed **by the database**, not the application, so
  the application cannot forge it (Task 6).

---

## Task list

| # | Task | Deliverable |
|---|---|---|
| 1 | Repo scaffolding, build tooling, CI skeleton | `./mvnw verify`, `uv run pytest`, `npm test` all green in CI |
| 2 | Operational schema, effective-dated (Flyway + Testcontainers) | Migrations apply; constraint tests pass |
| 3 | `policy_parameter_set` — effective-dated SNAP parameters + resolver | As-of-date resolution proven by test |
| 4 | DMN decision tables on Drools/KIE | Table-driven SNAP scenarios pass, incl. as-of-date correctness |
| 5 | Determination service — persists determination + trace | Determination + full trace in Postgres |
| 6 | Hash-chained audit log + CI verification job | Chain verifies; tamper detected; UPDATE/DELETE refused |
| 7 | Portal API — intake + worker case view (roles hardcoded) | Endpoint contract tests pass |
| 8 | React UI — intake form + worker case view | Vitest + RTL green |
| 9 | Synthetic applicant generator (ACS PUMS-driven) | Seeded, reproducible, distribution-tested |
| 10 | Ingestion + dbt bronze → silver → gold | dbt build + dbt test green |
| 11 | Reporting — gold to serving Postgres, Metabase, TMDL | Report page renders real numbers |
| 12 | Docker Compose — whole stack, one command | `make up` brings everything up healthy |
| 13 | End-to-end test + Phase 1a wrap-up | intake → determination → audit → warehouse → mart, in CI |

---

## Task 1: Repo scaffolding, build tooling, CI skeleton

Every later task assumes these three toolchains build and test from a clean
clone, and that CI proves it. Nothing domain-specific happens here — one
trivially-true test per language exists so the pipeline itself is verified
rather than asserted.

**Files:**
- Create: `pom.xml`, `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties`
- Create: `rules-engine/pom.xml`, `rules-engine/src/main/java/canopica/rules/package-info.java`
- Create: `portal/pom.xml`, `portal/src/main/java/canopica/portal/CanopicaPortalApplication.java`
- Create: `portal/src/main/resources/application.yml`
- Create: `portal/src/test/java/canopica/portal/CanopicaPortalApplicationTest.java`
- Create: `portal/web/` (Vite React TS scaffold), `portal/web/src/App.tsx`, `portal/web/src/App.test.tsx`
- Create: `data-platform/pyproject.toml`, `data-platform/src/canopica_data/__init__.py`, `data-platform/src/canopica_data/config.py`, `data-platform/tests/test_config.py`
- Create: `.github/workflows/ci.yml`, `Makefile`, `.editorconfig`, `.gitignore`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `canopica.portal` and `canopica.rules` Java packages; the `canopica_data` Python
  package with `canopica_data.config.Settings` (Pydantic v2 `BaseSettings`)
  exposing `operational_dsn: str`, `serving_dsn: str`, `warehouse_root: Path`;
  Make targets `build`, `test`, `lint`, `up`, `down`, `e2e`.

- [ ] **Step 1: Create the Maven aggregator and wrapper**

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>canopica</groupId>
  <artifactId>canopica-parent</artifactId>
  <version>0.1.0-SNAPSHOT</version>
  <packaging>pom</packaging>
  <name>Canopica</name>
  <modules>
    <module>rules-engine</module>
    <module>portal</module>
  </modules>
  <properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.boot.version>3.5.3</spring.boot.version>
    <kie.version>10.2.0</kie.version>
    <testcontainers.version>1.21.3</testcontainers.version>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-dependencies</artifactId>
        <version>${spring.boot.version}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
      <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-bom</artifactId>
        <version>${testcontainers.version}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
</project>
```

Then generate the committed wrapper (CI must not depend on a Maven install):

```bash
mvn -N wrapper:wrapper -Dmaven=3.9.16
```

- [ ] **Step 2: Create the `rules-engine` module (empty but building)**

`rules-engine/pom.xml` — parent `canopica-parent`, artifactId `rules-engine`,
dependencies `org.kie:kie-dmn-core:${kie.version}` and
`org.junit.jupiter:junit-jupiter` (test scope). Add
`src/main/java/canopica/rules/package-info.java` with a one-line package comment
so the module has a source root.

- [ ] **Step 3: Create the `portal` module with a failing context test**

`portal/src/test/java/canopica/portal/CanopicaPortalApplicationTest.java`:

```java
package canopica.portal;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = "spring.autoconfigure.exclude=" +
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
class CanopicaPortalApplicationTest {
    @Test
    void contextLoads() {
    }
}
```

- [ ] **Step 4: Run it and watch it fail**

Run: `./mvnw -pl portal test`
Expected: FAIL — `CanopicaPortalApplication` does not exist.

- [ ] **Step 5: Add the application class and `application.yml`**

```java
package canopica.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CanopicaPortalApplication {
    public static void main(String[] args) {
        SpringApplication.run(CanopicaPortalApplication.class, args);
    }
}
```

`portal/pom.xml` uses `spring-boot-starter-web`, `spring-boot-starter-data-jpa`,
`spring-boot-starter-validation`, `org.postgresql:postgresql`,
`org.flywaydb:flyway-core`, `org.flywaydb:flyway-database-postgresql`,
`canopica:rules-engine:${project.version}`, and test-scoped
`spring-boot-starter-test`, `org.testcontainers:postgresql`,
`org.testcontainers:junit-jupiter`. Include the `spring-boot-maven-plugin`.

`application.yml` reads connection settings from environment with
local-dev defaults:

```yaml
spring:
  datasource:
    url: ${CANOPICA_OPERATIONAL_JDBC_URL:jdbc:postgresql://localhost:5432/canopica_operational}
    username: ${CANOPICA_OPERATIONAL_USER:canopica_app}
    password: ${CANOPICA_OPERATIONAL_PASSWORD:canopica_app}
  jpa:
    hibernate.ddl-auto: validate
    open-in-view: false
  flyway:
    enabled: true
    locations: classpath:db/migration
canopica:
  timezone: America/New_York
```

- [ ] **Step 6: Run it and watch it pass**

Run: `./mvnw -pl portal test` → PASS.

- [ ] **Step 7: Scaffold the React app with one passing test**

```bash
cd portal/web && npm create vite@latest . -- --template react-ts
npm install
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom @vitest/coverage-v8
```

Set `vite.config.ts` `test: { environment: 'jsdom', globals: true, setupFiles: './src/test/setup.ts' }`,
add `"test": "vitest run"` and `"typecheck": "tsc --noEmit"` to
`package.json` scripts, and write `src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the Canopica application shell', () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: /Canopica/i })).toBeInTheDocument();
});
```

Reduce `App.tsx` to a shell rendering `<h1>Canopica</h1>` plus a placeholder
`<main>`; delete the Vite demo counter, logos, and CSS.

Run: `npm test` → PASS. Run: `npm run typecheck` → clean.

- [ ] **Step 8: Scaffold the Python data platform**

```bash
cd data-platform && uv init --package --name canopica-data --python 3.12
uv add pydantic pydantic-settings polars duckdb deltalake "psycopg[binary]" httpx
uv add --dev pytest ruff mypy types-requests
```

`pyproject.toml` must additionally carry:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "PL", "RUF"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
  "integration: needs a running Postgres (Docker)",
  "e2e: needs the full Compose stack",
]
```

`src/canopica_data/config.py`:

```python
"""Runtime configuration for the Canopica data platform."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings shared by every data-platform entry point."""

    model_config = SettingsConfigDict(env_prefix="CANOPICA_", env_file=".env", extra="ignore")

    operational_dsn: str = "postgresql://canopica_app:canopica_app@localhost:5432/canopica_operational"
    serving_dsn: str = "postgresql://canopica_app:canopica_app@localhost:5432/canopica_serving"
    warehouse_root: Path = Path("data-platform/warehouse")

    @property
    def bronze_root(self) -> Path:
        return self.warehouse_root / "bronze"
```

`tests/test_config.py`:

```python
from pathlib import Path

from canopica_data.config import Settings


def test_bronze_root_derives_from_warehouse_root() -> None:
    settings = Settings(warehouse_root=Path("/tmp/wh"))
    assert settings.bronze_root == Path("/tmp/wh/bronze")


def test_settings_read_env_prefix(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CANOPICA_SERVING_DSN", "postgresql://x/y")
    assert Settings().serving_dsn == "postgresql://x/y"
```

Run: `uv run pytest`, `uv run ruff check .`, `uv run mypy src tests` → all clean.

- [ ] **Step 9: Write the Makefile**

```make
.PHONY: build test lint up down e2e
build:      ; ./mvnw -B -q verify -DskipTests && cd portal/web && npm ci && npm run build
test:       ; ./mvnw -B verify && cd portal/web && npm test && cd ../../data-platform && uv run pytest -m "not integration and not e2e"
lint:       ; cd data-platform && uv run ruff check . && uv run mypy src tests && cd ../portal/web && npm run typecheck
up:         ; docker compose -f infra/docker-compose.yml up -d --build
down:       ; docker compose -f infra/docker-compose.yml down -v
e2e:        ; cd data-platform && uv run pytest -m e2e
```

- [ ] **Step 10: Write the CI workflow**

`.github/workflows/ci.yml` — four jobs on `push` and `pull_request`:

```yaml
name: CI
on: [push, pull_request]

jobs:
  java:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: '17', cache: maven }
      - run: ./mvnw -B verify

  web:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: portal/web } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: npm, cache-dependency-path: portal/web/package-lock.json }
      - run: npm ci
      - run: npm run typecheck
      - run: npm test

  python:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: data-platform } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --all-extras --dev
      - run: uv run ruff check .
      - run: uv run mypy src tests
      - run: uv run pytest -m "not e2e"
```

The `java` job runs Testcontainers tests from Task 2 onward — GitHub's
`ubuntu-latest` runners have a working Docker daemon, so no extra service
container is needed. Later tasks add `dbt`, `audit-chain`, and `e2e` jobs to
this same file.

- [ ] **Step 11: Verify the whole gate locally, then commit**

```bash
make test && make lint
```
Expected: Java, web, and Python suites all green.

Update `docs/STATUS.md`: Phase 1a table replaced by this plan's 13-task
list, Task 1 marked Done, a verification-log row added with the date, the
three suite results, and the commit hash placeholder filled in after commit.
Point "Next action" at Task 2.

```bash
git add -A
git commit -m "Task 1: repo scaffolding, Maven/uv/Vite toolchains, CI skeleton"
git push
```
Confirm the CI run is green before starting Task 2.

---

## Task 2: Operational schema, effective-dated

Implements roadmap §3.4.1 for the entities Phase 1a actually touches.
`policy_parameter_set` (Task 3), `eligibility_determination` /
`determination_trace` (Task 5), and `audit_event` (Task 6) get their own
migrations in their own tasks, so each commit stays self-contained.
`external_verification` and `notice` are Phase 1b/3 and are **not** created.

Two conventions applied throughout, stated once:

- **Enumerations are `text` + a `CHECK` constraint**, not Postgres `enum`
  types. Adding a value to a real enum type is a migration that cannot run
  inside a transaction on older servers; a `CHECK` is a one-line alter.
- **Effective dating is `effective_from date NOT NULL` +
  `effective_to date NULL`** (null = still in effect), with a
  `CHECK (effective_to IS NULL OR effective_to >= effective_from)` on every
  such table. Households report changes mid-month constantly; a model that
  only stores "current" cannot answer what was true in March (roadmap §3.5).

**Files:**
- Create: `portal/src/main/resources/db/migration/V1__core_entities.sql`
- Create: `portal/src/main/resources/db/migration/V2__intake_records.sql`
- Create: `portal/src/main/java/canopica/portal/domain/` — `Person`, `Household`,
  `HouseholdMember`, `Worker`, `CaseAssignment`, `Application`,
  `ProgramRequest`, `IncomeRecord`, `ExpenseRecord`, `LivingArrangement`,
  `WorkActivity`, `DisabilityRecord`, `Verification`, `BenefitMonth`
- Create: `portal/src/main/java/canopica/portal/repo/` — one Spring Data
  repository per aggregate root (`PersonRepository`, `HouseholdRepository`,
  `ApplicationRepository`, `ProgramRequestRepository`,
  `IncomeRecordRepository`, `ExpenseRecordRepository`,
  `LivingArrangementRepository`, `WorkActivityRepository`,
  `DisabilityRecordRepository`, `VerificationRepository`,
  `CaseAssignmentRepository`)
- Create: `portal/src/test/java/canopica/portal/AbstractPostgresTest.java`
- Create: `portal/src/test/java/canopica/portal/domain/SchemaMigrationTest.java`
- Create: `portal/src/test/java/canopica/portal/domain/EffectiveDatingConstraintTest.java`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: Task 1's `portal` module and `application.yml`.
- Produces: JPA entities in `canopica.portal.domain` (all with `UUID id`, all
  money as `BigDecimal`, all dates as `java.time.LocalDate`); the
  `AbstractPostgresTest` base class every later Testcontainers test extends;
  table and column names the dbt bronze layer sources verbatim in Task 10.

- [ ] **Step 1: Write the failing migration test**

`portal/src/test/java/canopica/portal/AbstractPostgresTest.java`:

```java
package canopica.portal;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
public abstract class AbstractPostgresTest {

    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("canopica_operational")
                    .withUsername("canopica_app")
                    .withPassword("canopica_app");

    static {
        POSTGRES.start(); // singleton container, reused by every subclass
    }

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }
}
```

`SchemaMigrationTest.java`:

```java
package canopica.portal.domain;

import static org.assertj.core.api.Assertions.assertThat;

import canopica.portal.AbstractPostgresTest;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class SchemaMigrationTest extends AbstractPostgresTest {

    @Autowired JdbcTemplate jdbc;

    @Test
    void everyPhase1aOperationalTableExists() {
        List<String> tables = jdbc.queryForList(
                "select table_name from information_schema.tables where table_schema = 'public'",
                String.class);
        assertThat(tables).contains(
                "person", "household", "household_member", "worker", "case_assignment",
                "application", "program_request", "income_record", "expense_record",
                "living_arrangement", "work_activity", "disability_record",
                "verification", "benefit_month");
    }

    @Test
    void everyEffectiveDatedTableCarriesBothDateColumns() {
        List<String> effectiveDated = List.of(
                "household_member", "income_record", "expense_record",
                "living_arrangement", "work_activity", "disability_record",
                "case_assignment");
        for (String table : effectiveDated) {
            List<String> columns = jdbc.queryForList(
                    "select column_name from information_schema.columns "
                            + "where table_schema = 'public' and table_name = ?",
                    String.class, table);
            assertThat(columns)
                    .as("effective dating on %s", table)
                    .contains("effective_from", "effective_to");
        }
    }
}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `./mvnw -pl portal test -Dtest=SchemaMigrationTest`
Expected: FAIL — no tables exist (Flyway has no migrations yet).

- [ ] **Step 3: Write `V1__core_entities.sql`**

```sql
-- Core party and caseload entities. All identifiers are UUIDs generated by
-- the application, so a record's identity does not depend on insert order.

create table person (
    id                  uuid primary key,
    first_name          text        not null,
    last_name           text        not null,
    date_of_birth       date        not null,
    -- Tokenized stand-in for an SSN-like identifier. The real value never
    -- exists in this system; the token is what the warehouse ever sees.
    ssn_token           text        not null unique,
    sex                 text        not null check (sex in ('F', 'M', 'X')),
    is_us_citizen       boolean     not null default true,
    created_at          timestamptz not null default now()
);

create table household (
    id                  uuid primary key,
    -- The person whose circumstances anchor the case. Head-of-household is a
    -- real SNAP concept, not a UI convenience.
    head_person_id      uuid        not null references person (id),
    county              text        not null,
    created_at          timestamptz not null default now()
);

create table household_member (
    id                  uuid primary key,
    household_id        uuid        not null references household (id),
    person_id           uuid        not null references person (id),
    relationship        text        not null check (relationship in
                            ('SELF', 'SPOUSE', 'CHILD', 'PARENT', 'OTHER_RELATIVE', 'UNRELATED')),
    purchases_and_prepares_food_together boolean not null default true,
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint household_member_effective_range check (effective_to is null or effective_to >= effective_from),
    constraint household_member_unique_span unique (household_id, person_id, effective_from)
);

create table worker (
    id                  uuid primary key,
    full_name           text        not null,
    email               text        not null unique,
    role                text        not null check (role in ('WORKER', 'SUPERVISOR', 'ADMIN')),
    created_at          timestamptz not null default now()
);

-- CASE_ASSIGNMENT is what makes caseload-scoped authorization possible at
-- all in Phase 1b. Created now because determinations reference the worker
-- who is accountable for the case.
create table case_assignment (
    id                  uuid primary key,
    household_id        uuid        not null references household (id),
    worker_id           uuid        not null references worker (id),
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint case_assignment_effective_range check (effective_to is null or effective_to >= effective_from)
);

create index household_member_household_idx on household_member (household_id, effective_from);
create index case_assignment_household_idx on case_assignment (household_id, effective_from);
```

- [ ] **Step 4: Write `V2__intake_records.sql`**

```sql
create table application (
    id                  uuid primary key,
    household_id        uuid        not null references household (id),
    submitted_at        timestamptz not null,
    channel             text        not null check (channel in ('ONLINE', 'PHONE', 'PAPER', 'IN_PERSON')),
    created_at          timestamptz not null default now()
);

-- PROGRAM_REQUEST is the unit of eligibility, not APPLICATION: one
-- application commonly requests several programs, each determined
-- separately, on its own timeline, with its own outcome (roadmap §3.4.1).
create table program_request (
    id                  uuid primary key,
    application_id      uuid        not null references application (id),
    program_code        text        not null check (program_code in ('SNAP')),
    status              text        not null check (status in
                            ('SUBMITTED', 'PENDING_VERIFICATION', 'DETERMINED', 'WITHDRAWN')),
    requested_on        date        not null,
    -- SNAP's federal processing standards: 30 days normal, 7 days expedited.
    -- Stored per request because expedited status is determined per request.
    is_expedited        boolean     not null default false,
    created_at          timestamptz not null default now(),
    constraint program_request_unique_per_application unique (application_id, program_code)
);

create table income_record (
    id                  uuid primary key,
    person_id           uuid        not null references person (id),
    income_type         text        not null check (income_type in
                            ('WAGES', 'SELF_EMPLOYMENT', 'UNEMPLOYMENT', 'SOCIAL_SECURITY',
                             'SSI', 'CHILD_SUPPORT', 'PENSION', 'OTHER_UNEARNED')),
    -- Whether this counts as earned income drives the 20% earned-income
    -- deduction, so it is stored, not inferred at evaluation time.
    is_earned           boolean     not null,
    monthly_amount      numeric(12, 2) not null check (monthly_amount >= 0),
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint income_record_effective_range check (effective_to is null or effective_to >= effective_from)
);

create table expense_record (
    id                  uuid primary key,
    person_id           uuid        not null references person (id),
    expense_type        text        not null check (expense_type in
                            ('RENT_OR_MORTGAGE', 'PROPERTY_TAX', 'HOME_INSURANCE', 'UTILITIES',
                             'DEPENDENT_CARE', 'MEDICAL', 'CHILD_SUPPORT_PAID')),
    monthly_amount      numeric(12, 2) not null check (monthly_amount >= 0),
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint expense_record_effective_range check (effective_to is null or effective_to >= effective_from)
);

create table living_arrangement (
    id                  uuid primary key,
    household_id        uuid        not null references household (id),
    arrangement_type    text        not null check (arrangement_type in
                            ('RENTS', 'OWNS', 'HOMELESS', 'SHARED_HOUSING', 'INSTITUTION')),
    pays_utilities_separately boolean not null default false,
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint living_arrangement_effective_range check (effective_to is null or effective_to >= effective_from)
);

create table work_activity (
    id                  uuid primary key,
    person_id           uuid        not null references person (id),
    activity_type       text        not null check (activity_type in
                            ('EMPLOYED', 'SEEKING_WORK', 'IN_TRAINING', 'STUDENT', 'NOT_WORKING')),
    weekly_hours        integer     not null default 0 check (weekly_hours >= 0),
    exemption_reason    text check (exemption_reason in
                            ('ELDERLY', 'DISABLED', 'CARETAKER', 'STUDENT', 'PREGNANT', 'NONE')),
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint work_activity_effective_range check (effective_to is null or effective_to >= effective_from)
);

create table disability_record (
    id                  uuid primary key,
    person_id           uuid        not null references person (id),
    -- "Disabled" for SNAP purposes is a specific definition tied to receipt
    -- of a qualifying benefit, not a self-reported status.
    basis               text        not null check (basis in
                            ('SSI', 'SSDI', 'VA_DISABILITY', 'STATE_DISABILITY', 'MEDICAID_DISABILITY')),
    effective_from      date        not null,
    effective_to        date,
    created_at          timestamptz not null default now(),
    constraint disability_record_effective_range check (effective_to is null or effective_to >= effective_from)
);

create table verification (
    id                  uuid primary key,
    program_request_id  uuid        not null references program_request (id),
    data_element        text        not null check (data_element in
                            ('IDENTITY', 'RESIDENCY', 'INCOME', 'SHELTER_COST', 'MEDICAL_EXPENSE',
                             'DISABILITY', 'HOUSEHOLD_COMPOSITION')),
    status              text        not null check (status in ('OUTSTANDING', 'RECEIVED', 'WAIVED')),
    due_on              date        not null,
    satisfied_on        date,
    created_at          timestamptz not null default now()
);

create table benefit_month (
    id                  uuid primary key,
    program_request_id  uuid        not null references program_request (id),
    -- Always the first of the month; benefits are computed per benefit month.
    benefit_month       date        not null,
    created_at          timestamptz not null default now(),
    constraint benefit_month_is_first_of_month check (extract(day from benefit_month) = 1),
    constraint benefit_month_unique unique (program_request_id, benefit_month)
);

create index income_record_person_idx on income_record (person_id, effective_from);
create index expense_record_person_idx on expense_record (person_id, effective_from);
create index program_request_application_idx on program_request (application_id);
create index verification_request_idx on verification (program_request_id, status);
```

- [ ] **Step 5: Run the migration test and watch it pass**

Run: `./mvnw -pl portal test -Dtest=SchemaMigrationTest` → PASS.

- [ ] **Step 6: Write the constraint test, then the JPA entities**

`EffectiveDatingConstraintTest.java` asserts the database refuses bad data —
these are constraints, so they are tested against the database, not mocked:

```java
package canopica.portal.domain;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import canopica.portal.AbstractPostgresTest;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

class EffectiveDatingConstraintTest extends AbstractPostgresTest {

    @Autowired JdbcTemplate jdbc;

    @Test
    void rejectsAnEffectiveToBeforeItsEffectiveFrom() {
        UUID personId = insertPerson();
        assertThatThrownBy(() -> jdbc.update(
                "insert into income_record (id, person_id, income_type, is_earned, "
                        + "monthly_amount, effective_from, effective_to) "
                        + "values (?, ?, 'WAGES', true, 1000.00, date '2026-03-01', date '2026-02-01')",
                UUID.randomUUID(), personId))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void rejectsABenefitMonthThatIsNotTheFirstOfTheMonth() {
        UUID requestId = insertProgramRequest();
        assertThatThrownBy(() -> jdbc.update(
                "insert into benefit_month (id, program_request_id, benefit_month) "
                        + "values (?, ?, date '2026-03-15')",
                UUID.randomUUID(), requestId))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    // insertPerson() / insertProgramRequest() are private helpers in this test
    // class that insert the minimum valid parent rows and return their ids.
}
```

Then write the JPA entities. Every entity: `@Entity`, `@Table(name = "...")`,
`@Id UUID id`, `BigDecimal` for money, `LocalDate` for effective dating,
`Instant createdAt`. No `@OneToMany` collections in Phase 1a — repositories
query by foreign key explicitly, which keeps fetch behavior obvious and
avoids N+1 surprises in the determination path. Example:

```java
package canopica.portal.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

@Entity
@Table(name = "income_record")
public class IncomeRecord {
    @Id private UUID id;
    @Column(name = "person_id", nullable = false) private UUID personId;
    @Column(name = "income_type", nullable = false) private String incomeType;
    @Column(name = "is_earned", nullable = false) private boolean earned;
    @Column(name = "monthly_amount", nullable = false) private BigDecimal monthlyAmount;
    @Column(name = "effective_from", nullable = false) private LocalDate effectiveFrom;
    @Column(name = "effective_to") private LocalDate effectiveTo;
    @Column(name = "created_at", insertable = false, updatable = false) private Instant createdAt;
    // protected no-arg constructor, all-args constructor, getters; no setters.
}
```

Repositories carry the as-of queries the determination service needs:

```java
public interface IncomeRecordRepository extends JpaRepository<IncomeRecord, UUID> {

    @Query("""
        select r from IncomeRecord r
        where r.personId in :personIds
          and r.effectiveFrom <= :asOf
          and (r.effectiveTo is null or r.effectiveTo >= :asOf)
        """)
    List<IncomeRecord> findEffectiveOn(
            @Param("personIds") Collection<UUID> personIds, @Param("asOf") LocalDate asOf);
}
```

- [ ] **Step 7: Add an entity-mapping test**

`spring.jpa.hibernate.ddl-auto: validate` (set in Task 1) already fails
startup on any entity/table mismatch, so `SchemaMigrationTest` extending
`AbstractPostgresTest` proves the mapping. Add one round-trip test per
effective-dated repository asserting `findEffectiveOn` excludes a record
whose `effective_to` predates the as-of date and includes an open-ended one.

- [ ] **Step 8: Run the full suite and commit**

```bash
make test && make lint
```

Update `docs/STATUS.md` (Task 2 → Done, verification row). Commit:

```bash
git commit -am "Task 2: effective-dated operational schema with Flyway and Testcontainers"
```

---

## Task 3: `policy_parameter_set` — effective-dated SNAP parameters + resolver

Federal SNAP figures change on a fixed annual date (October 1). A
determination made in June 2025 must still reproduce, years later, against
the figures in force in June 2025 — that is the whole point of roadmap §3.5,
and Phase 4's QC assistant is unimplementable without it.

**Design decision, stated once and enforced everywhere after this:**
*numbers* live here, effective-dated and immutable once published; *logic*
lives in the DMN model (Task 4). Household-size lookups (standard deduction
by size, max allotment by size, income limits by size) are numbers, so they
resolve here, before the DMN call.

**Files:**
- Create: `portal/src/main/resources/db/migration/V3__policy_parameter_set.sql`
- Create: `portal/src/main/resources/db/migration/V4__seed_snap_parameters.sql`
- Create: `portal/src/main/java/canopica/portal/domain/PolicyParameterSet.java`,
  `PolicyParameter.java`
- Create: `portal/src/main/java/canopica/portal/repo/PolicyParameterSetRepository.java`,
  `PolicyParameterRepository.java`
- Create: `portal/src/main/java/canopica/portal/policy/PolicyParameterResolver.java`
- Create: `portal/src/main/java/canopica/portal/policy/PolicyParameterNotFoundException.java`
- Create: `rules-engine/src/main/java/canopica/rules/SnapPolicyParameters.java`
- Create: `portal/src/test/java/canopica/portal/policy/PolicyParameterResolverTest.java`
- Create: `portal/src/test/java/canopica/portal/policy/PolicyParameterImmutabilityTest.java`
- Create: `docs/design/policy-parameter-provenance.md`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: Task 2's schema and `AbstractPostgresTest`.
- Produces:

```java
package canopica.rules;

/** Every SNAP figure the DMN model needs, already resolved for one household
 *  size as of one decision date. Immutable; carries the version that produced
 *  it so a determination can record exactly what it used. */
public record SnapPolicyParameters(
        String parameterSetVersion,     // e.g. "SNAP-FY2025"
        java.util.UUID parameterSetId,
        java.math.BigDecimal grossIncomeLimit,
        java.math.BigDecimal netIncomeLimit,
        java.math.BigDecimal standardDeduction,
        java.math.BigDecimal earnedIncomeDeductionRate,
        java.math.BigDecimal medicalExpenseThreshold,
        java.math.BigDecimal excessShelterCap,
        java.math.BigDecimal shelterIncomeShare,
        java.math.BigDecimal maxAllotment,
        java.math.BigDecimal minimumBenefit,
        int minimumBenefitMaxHouseholdSize,
        java.math.BigDecimal benefitReductionRate) {}
```

```java
public interface PolicyParameterResolver {
    /** @throws PolicyParameterNotFoundException if no published set covers asOf. */
    SnapPolicyParameters resolveSnap(java.time.LocalDate asOf, int householdSize);
}
```

- [ ] **Step 1: Retrieve the authoritative figures and record their provenance**

Before writing any seed data, retrieve both fiscal years' figures from USDA
FNS's published Cost-of-Living Adjustment memoranda (the same public
documents that become Phase 2's RAG corpus) — the FY2025 memo effective
2024-10-01 and the FY2026 memo effective 2025-10-01, 48 states and DC.

Write `docs/design/policy-parameter-provenance.md` recording, per fiscal
year: the document title, its URL, the date retrieved, and every figure
transcribed. This file is the citation the seed migration points at, and it
is what makes "authentic, not invented" checkable by a reader.

The FY2025 values below are the expected content — **verify each against the
memo and correct any that differ before committing.** Do not seed a figure
that is not in the provenance doc.

| Parameter | HH size | FY2025 (48 states + DC) |
|---|---|---|
| `MAX_ALLOTMENT` | 1 / 2 / 3 / 4 | 292 / 536 / 768 / 975 |
| `MAX_ALLOTMENT` | 5 / 6 / 7 / 8 | 1158 / 1390 / 1536 / 1756 |
| `MAX_ALLOTMENT` | each additional | +220 |
| `STANDARD_DEDUCTION` | 1–3 / 4 / 5 / 6+ | 204 / 217 / 254 / 291 |
| `GROSS_INCOME_LIMIT` (130% FPL, monthly) | 1 / 2 / 3 / 4 | 1632 / 2215 / 2798 / 3380 |
| `GROSS_INCOME_LIMIT` | 5 / 6 / 7 / 8 | 3963 / 4546 / 5129 / 5712 |
| `NET_INCOME_LIMIT` (100% FPL, monthly) | 1 / 2 / 3 / 4 | 1255 / 1704 / 2152 / 2600 |
| `NET_INCOME_LIMIT` | 5 / 6 / 7 / 8 | 3049 / 3497 / 3945 / 4394 |
| `EXCESS_SHELTER_CAP` | — | 712 |
| `MINIMUM_BENEFIT` | — | 23 |
| `MINIMUM_BENEFIT_MAX_HOUSEHOLD_SIZE` | — | 2 |
| `MEDICAL_EXPENSE_THRESHOLD` | — | 35 (statutory) |
| `EARNED_INCOME_DEDUCTION_RATE` | — | 0.20 (statutory) |
| `BENEFIT_REDUCTION_RATE` | — | 0.30 (statutory) |
| `SHELTER_INCOME_SHARE` | — | 0.50 (statutory) |

Phase 1a seeds household sizes 1 through 8 only, and rejects a larger
household with a clear error rather than silently extrapolating — the
"+ each additional person" arithmetic is real policy and belongs in the
parameter model, not in a resolver's implicit fallback. Widening it is
Phase 1b work.

- [ ] **Step 2: Write the failing resolver test**

```java
package canopica.portal.policy;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import canopica.portal.AbstractPostgresTest;
import java.math.BigDecimal;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class PolicyParameterResolverTest extends AbstractPostgresTest {

    @Autowired PolicyParameterResolver resolver;

    @Test
    void resolvesTheFiscalYearInForceOnTheDecisionDate() {
        var june2025 = resolver.resolveSnap(LocalDate.of(2025, 6, 15), 3);
        assertThat(june2025.parameterSetVersion()).isEqualTo("SNAP-FY2025");
        assertThat(june2025.maxAllotment()).isEqualByComparingTo("768");
        assertThat(june2025.standardDeduction()).isEqualByComparingTo("204");
    }

    @Test
    void resolvesTheNextFiscalYearOnAndAfterOctoberFirst() {
        var oct2025 = resolver.resolveSnap(LocalDate.of(2025, 10, 1), 3);
        assertThat(oct2025.parameterSetVersion()).isEqualTo("SNAP-FY2026");
    }

    @Test
    void theBoundaryIsExactAndNotOffByOneDay() {
        assertThat(resolver.resolveSnap(LocalDate.of(2025, 9, 30), 3).parameterSetVersion())
                .isEqualTo("SNAP-FY2025");
    }

    @Test
    void sizeScopedParametersDifferBySizeWhileScalarsDoNot() {
        var one = resolver.resolveSnap(LocalDate.of(2025, 6, 15), 1);
        var six = resolver.resolveSnap(LocalDate.of(2025, 6, 15), 6);
        assertThat(one.standardDeduction()).isEqualByComparingTo("204");
        assertThat(six.standardDeduction()).isEqualByComparingTo("291");
        assertThat(one.earnedIncomeDeductionRate())
                .isEqualByComparingTo(six.earnedIncomeDeductionRate());
    }

    @Test
    void rejectsAHouseholdSizeTheParameterSetDoesNotCover() {
        assertThatThrownBy(() -> resolver.resolveSnap(LocalDate.of(2025, 6, 15), 9))
                .isInstanceOf(PolicyParameterNotFoundException.class)
                .hasMessageContaining("household size 9");
    }

    @Test
    void rejectsADateNoPublishedSetCovers() {
        assertThatThrownBy(() -> resolver.resolveSnap(LocalDate.of(2019, 1, 1), 3))
                .isInstanceOf(PolicyParameterNotFoundException.class);
    }
}
```

- [ ] **Step 3: Run it and watch it fail**

Run: `./mvnw -pl portal test -Dtest=PolicyParameterResolverTest`
Expected: FAIL — `PolicyParameterResolver` does not exist.

- [ ] **Step 4: Write `V3__policy_parameter_set.sql`**

```sql
create table policy_parameter_set (
    id                  uuid primary key,
    program_code        text        not null check (program_code in ('SNAP')),
    version_label       text        not null unique,        -- e.g. 'SNAP-FY2025'
    effective_from      date        not null,
    effective_to        date,                                -- null = still in force
    source_citation     text        not null,                -- title + URL of the published memo
    retrieved_on        date        not null,
    published_at        timestamptz not null default now(),
    constraint policy_parameter_set_effective_range check (effective_to is null or effective_to >= effective_from),
    constraint policy_parameter_set_unique_span unique (program_code, effective_from)
);

create table policy_parameter (
    id                  uuid primary key,
    parameter_set_id    uuid        not null references policy_parameter_set (id),
    name                text        not null,
    -- null household_size = the parameter is scalar (a rate, a threshold);
    -- non-null = the value applies to exactly that household size.
    household_size      integer     check (household_size is null or household_size between 1 and 8),
    numeric_value       numeric(12, 4) not null,
    unit                text        not null check (unit in ('USD_PER_MONTH', 'RATE', 'COUNT')),
    constraint policy_parameter_unique unique (parameter_set_id, name, household_size)
);

-- A published parameter set is immutable. Not "by convention" — the database
-- refuses. Reproducing a 2025 determination in 2030 depends on this holding.
create or replace function policy_parameter_set_is_immutable() returns trigger
language plpgsql as $$
begin
    raise exception 'policy_parameter_set rows are immutable once published (attempted %)', tg_op;
end;
$$;

create trigger policy_parameter_set_no_mutation
    before update or delete on policy_parameter_set
    for each row execute function policy_parameter_set_is_immutable();

create trigger policy_parameter_no_mutation
    before update or delete on policy_parameter
    for each row execute function policy_parameter_set_is_immutable();

create index policy_parameter_lookup_idx on policy_parameter (parameter_set_id, name, household_size);
```

Superseding a fiscal year is therefore an *insert* of the next set plus a
correction migration — never an in-place edit. Because `effective_to` cannot
be updated either, each set's `effective_to` is written at insert time by the
migration that introduces its successor's predecessor boundary; the FY2025
row is seeded with `effective_to = date '2025-09-30'` from the start.

- [ ] **Step 5: Write `V4__seed_snap_parameters.sql`**

Seeds both sets from the verified provenance doc. Shape:

```sql
insert into policy_parameter_set (id, program_code, version_label, effective_from,
                                  effective_to, source_citation, retrieved_on)
values ('9f1c0e10-0000-4000-8000-000000000001', 'SNAP', 'SNAP-FY2025',
        date '2024-10-01', date '2025-09-30',
        '<exact title and URL from docs/design/policy-parameter-provenance.md>',
        date '<retrieval date>');

insert into policy_parameter (id, parameter_set_id, name, household_size, numeric_value, unit)
values
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MAX_ALLOTMENT', 1, 292, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MAX_ALLOTMENT', 2, 536, 'USD_PER_MONTH'),
  -- … sizes 3–8 …
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'STANDARD_DEDUCTION', 1, 204, 'USD_PER_MONTH'),
  -- … sizes 2–8 (1–3 share 204; 4 = 217; 5 = 254; 6, 7, 8 = 291) …
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'GROSS_INCOME_LIMIT', 1, 1632, 'USD_PER_MONTH'),
  -- … sizes 2–8 …
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'NET_INCOME_LIMIT', 1, 1255, 'USD_PER_MONTH'),
  -- … sizes 2–8 …
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'EXCESS_SHELTER_CAP', null, 712, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MINIMUM_BENEFIT', null, 23, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MINIMUM_BENEFIT_MAX_HOUSEHOLD_SIZE', null, 2, 'COUNT'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'MEDICAL_EXPENSE_THRESHOLD', null, 35, 'USD_PER_MONTH'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'EARNED_INCOME_DEDUCTION_RATE', null, 0.20, 'RATE'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'BENEFIT_REDUCTION_RATE', null, 0.30, 'RATE'),
  (gen_random_uuid(), '9f1c0e10-0000-4000-8000-000000000001', 'SHELTER_INCOME_SHARE', null, 0.50, 'RATE');
```

Then the same block for `SNAP-FY2026`, id
`9f1c0e10-0000-4000-8000-000000000002`, `effective_from date '2025-10-01'`,
`effective_to null`, with that memo's figures.

`gen_random_uuid()` is built into Postgres 13+; no extension needed.

- [ ] **Step 6: Implement the resolver**

```java
package canopica.portal.policy;

import canopica.rules.SnapPolicyParameters;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
class JdbcPolicyParameterResolver implements PolicyParameterResolver {

    private static final List<String> SIZE_SCOPED =
            List.of("MAX_ALLOTMENT", "STANDARD_DEDUCTION", "GROSS_INCOME_LIMIT", "NET_INCOME_LIMIT");

    private final PolicyParameterSetRepository sets;
    private final PolicyParameterRepository parameters;

    // constructor omitted for brevity in this plan; standard constructor injection

    @Override
    public SnapPolicyParameters resolveSnap(LocalDate asOf, int householdSize) {
        var set = sets.findEffectiveOn("SNAP", asOf).orElseThrow(() ->
                new PolicyParameterNotFoundException(
                        "no published SNAP parameter set covers " + asOf));

        // One query, then an in-memory index: a determination resolves ~14
        // parameters and should not issue 14 round trips.
        Map<String, BigDecimal> byName = parameters
                .findForSet(set.getId(), householdSize)
                .stream()
                .collect(java.util.stream.Collectors.toMap(
                        PolicyParameter::getName, PolicyParameter::getNumericValue));

        for (String required : SIZE_SCOPED) {
            if (!byName.containsKey(required)) {
                throw new PolicyParameterNotFoundException(
                        set.getVersionLabel() + " does not cover household size " + householdSize
                                + " (missing " + required + ")");
            }
        }

        return new SnapPolicyParameters(
                set.getVersionLabel(), set.getId(),
                byName.get("GROSS_INCOME_LIMIT"), byName.get("NET_INCOME_LIMIT"),
                byName.get("STANDARD_DEDUCTION"), byName.get("EARNED_INCOME_DEDUCTION_RATE"),
                byName.get("MEDICAL_EXPENSE_THRESHOLD"), byName.get("EXCESS_SHELTER_CAP"),
                byName.get("SHELTER_INCOME_SHARE"), byName.get("MAX_ALLOTMENT"),
                byName.get("MINIMUM_BENEFIT"),
                byName.get("MINIMUM_BENEFIT_MAX_HOUSEHOLD_SIZE").intValueExact(),
                byName.get("BENEFIT_REDUCTION_RATE"));
    }
}
```

`PolicyParameterSetRepository.findEffectiveOn` is
`where program_code = :code and effective_from <= :asOf and (effective_to is null or effective_to >= :asOf)`.
`PolicyParameterRepository.findForSet` is
`where parameter_set_id = :setId and (household_size is null or household_size = :size)`.

- [ ] **Step 7: Run the resolver test and watch it pass**

Run: `./mvnw -pl portal test -Dtest=PolicyParameterResolverTest` → PASS (all six).

- [ ] **Step 8: Prove immutability is enforced by the database**

```java
class PolicyParameterImmutabilityTest extends AbstractPostgresTest {

    @Autowired JdbcTemplate jdbc;

    @Test
    void refusesToUpdateAPublishedParameter() {
        assertThatThrownBy(() -> jdbc.update(
                "update policy_parameter set numeric_value = 999 where name = 'MINIMUM_BENEFIT'"))
                .hasMessageContaining("immutable once published");
    }

    @Test
    void refusesToDeleteAPublishedParameterSet() {
        assertThatThrownBy(() -> jdbc.update(
                "delete from policy_parameter_set where version_label = 'SNAP-FY2025'"))
                .hasMessageContaining("immutable once published");
    }
}
```

Run: `./mvnw -pl portal test -Dtest=PolicyParameterImmutabilityTest` → PASS.

- [ ] **Step 9: Run the full suite and commit**

```bash
make test && make lint
git add -A && git commit -m "Task 3: effective-dated SNAP policy parameter sets and as-of resolver"
```

`docs/STATUS.md` updated in this same commit.

---

## Task 4: DMN decision tables on Drools/KIE

The rules engine is a pure library: facts in, decision plus trace out. No
Spring, no database, no clock of its own. Everything temporal was resolved by
Task 3 before the call. That is what makes it table-driven testable and what
makes the same evaluation reproducible years later.

**Files:**
- Create: `rules-engine/src/main/resources/dmn/snap-eligibility.dmn`
- Create: `rules-engine/src/main/java/canopica/rules/SnapFacts.java`
- Create: `rules-engine/src/main/java/canopica/rules/SnapDecision.java`
- Create: `rules-engine/src/main/java/canopica/rules/SnapDmnEvaluator.java`
- Create: `rules-engine/src/main/java/canopica/rules/DmnEvaluationException.java`
- Create: `rules-engine/src/test/java/canopica/rules/DmnModelSanityTest.java`
- Create: `rules-engine/src/test/java/canopica/rules/SnapDmnEvaluatorTest.java`
- Create: `rules-engine/src/test/java/canopica/rules/TestFixtures.java` (a `facts()`
  builder defaulting every amount to zero, and `fy2025Parameters(size)` /
  `parameters(size)` builders holding the Task 3 table as literals)
- Create: `rules-engine/README.md` (the decision graph, in prose, for a reader)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: `canopica.rules.SnapPolicyParameters` (Task 3).
- Produces:

```java
package canopica.rules;

import java.math.BigDecimal;

/** One household's circumstances as of one decision date, already resolved
 *  from effective-dated records by the caller. All amounts are monthly. */
public record SnapFacts(
        int householdSize,
        BigDecimal earnedIncome,
        BigDecimal unearnedIncome,
        BigDecimal dependentCareCost,
        BigDecimal medicalExpense,
        BigDecimal shelterCost,
        BigDecimal utilityCost,
        boolean hasElderlyOrDisabledMember,
        boolean categoricallyEligible) {}
```

```java
package canopica.rules;

import java.math.BigDecimal;
import java.util.Map;

/** @param trace every named DMN decision's result, in evaluation order.
 *               Persisted verbatim as DETERMINATION_TRACE (Task 5). */
public record SnapDecision(
        boolean eligible,
        BigDecimal benefitAmount,
        String reasonCode,          // ELIGIBLE | GROSS_INCOME_EXCEEDS_LIMIT
                                    // | NET_INCOME_EXCEEDS_LIMIT | ZERO_BENEFIT_AMOUNT
        Map<String, Object> trace) {}
```

```java
public final class SnapDmnEvaluator {
    public SnapDmnEvaluator();                                  // loads the model once
    public SnapDecision evaluate(SnapFacts facts, SnapPolicyParameters parameters);
}
```

### The decision graph

Two input data nodes, `Facts` and `Parameters`, matching the two records
above field for field. Fifteen decisions, each individually named so each one
lands in the trace:

| # | Decision | Kind | Logic |
|---|---|---|---|
| 1 | `Gross Income` | literal | `Facts.earnedIncome + Facts.unearnedIncome` |
| 2 | `Gross Test Exempt` | literal | `Facts.hasElderlyOrDisabledMember or Facts.categoricallyEligible` |
| 3 | `Gross Income Within Limit` | literal | `Gross Income <= Parameters.grossIncomeLimit` |
| 4 | `Gross Income Test` | decision table (U) | `Gross Test Exempt` = true → `"EXEMPT"`; false + within = true → `"PASS"`; false + within = false → `"FAIL"` |
| 5 | `Earned Income Deduction` | literal | `Facts.earnedIncome * Parameters.earnedIncomeDeductionRate` |
| 6 | `Dependent Care Deduction` | literal | `Facts.dependentCareCost` |
| 7 | `Medical Expense Deduction` | decision table (U) | elderly/disabled = true → `max([0, Facts.medicalExpense - Parameters.medicalExpenseThreshold])`; false → `0` |
| 8 | `Adjusted Income` | literal | `max([0, Gross Income - Parameters.standardDeduction - Earned Income Deduction - Dependent Care Deduction - Medical Expense Deduction])` |
| 9 | `Total Shelter Cost` | literal | `Facts.shelterCost + Facts.utilityCost` |
| 10 | `Shelter Excess` | literal | `max([0, Total Shelter Cost - Parameters.shelterIncomeShare * Adjusted Income])` |
| 11 | `Excess Shelter Deduction` | decision table (U) | elderly/disabled = true → `Shelter Excess` (uncapped, real policy); false → `min([Shelter Excess, Parameters.excessShelterCap])` |
| 12 | `Net Income` | literal | `max([0, Adjusted Income - Excess Shelter Deduction])` |
| 13 | `Net Income Test` | decision table (U) | `Facts.categoricallyEligible` = true → `"EXEMPT"`; false + `Net Income <= Parameters.netIncomeLimit` → `"PASS"`; false + otherwise → `"FAIL"` |
| 14 | `Benefit Amount` | decision table (F) | see below |
| 15 | `Determination` | context | `{ eligible: ..., benefitAmount: Benefit Amount, reasonCode: ... }` |

`Benefit Amount` (hit policy FIRST — the rows are ordered and the first match
wins, which is exactly how the minimum-benefit rule reads in policy):

| # | Gross Income Test | Net Income Test | `Computed Benefit` | Household size | Output |
|---|---|---|---|---|---|
| 1 | `"FAIL"` | – | – | – | `0` |
| 2 | – | `"FAIL"` | – | – | `0` |
| 3 | – | – | `> 0` | – | `Computed Benefit` |
| 4 | – | – | `<= 0` | `<= Parameters.minimumBenefitMaxHouseholdSize` | `Parameters.minimumBenefit` |
| 5 | – | – | – | – | `0` |

where `Computed Benefit` is decision 14a, a literal expression:
`max([0, Parameters.maxAllotment - ceiling(Net Income * Parameters.benefitReductionRate)])`.
`ceiling` is FEEL's built-in; rounding the 30% share *up* to the whole dollar
before subtracting is the published SNAP arithmetic, not a floating-point
convenience.

`Determination` (decision 15) is a FEEL context:

```
{
  eligible:      Gross Income Test != "FAIL" and Net Income Test != "FAIL" and Benefit Amount > 0,
  benefitAmount: Benefit Amount,
  reasonCode:    if Gross Income Test = "FAIL" then "GROSS_INCOME_EXCEEDS_LIMIT"
                 else if Net Income Test = "FAIL" then "NET_INCOME_EXCEEDS_LIMIT"
                 else if Benefit Amount <= 0 then "ZERO_BENEFIT_AMOUNT"
                 else "ELIGIBLE"
}
```

A three-or-more-person household whose computed benefit is zero is a denial,
not a $0 award — that is what row 5 plus `ZERO_BENEFIT_AMOUNT` encode.

**Deliberately out of Phase 1a scope, named so nobody assumes otherwise:**
the asset/resource test, the child-support-paid deduction, the homeless
shelter deduction, state utility allowance variation, and ABAWD work
requirements. Each is a decision to add to this same model later, not a
redesign.

- [ ] **Step 1: Write the model sanity test first**

This test exists because the `kie-dmn` bootstrap API is the one thing in this
task that cannot be verified by reading — get it wrong and every later test
fails confusingly.

```java
package canopica.rules;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class DmnModelSanityTest {

    @Test
    void theModelLoadsWithNoCompilationMessages() {
        SnapDmnEvaluator evaluator = new SnapDmnEvaluator();
        assertThat(evaluator.modelMessages())
                .as("DMN compilation messages")
                .isEmpty();
    }

    @Test
    void everyNamedDecisionAppearsInTheTraceOfATrivialEvaluation() {
        SnapDecision decision = new SnapDmnEvaluator().evaluate(
                TestFixtures.facts().householdSize(1).build(),
                TestFixtures.fy2025Parameters(1));
        assertThat(decision.trace()).containsKeys(
                "Gross Income", "Gross Income Test", "Earned Income Deduction",
                "Medical Expense Deduction", "Adjusted Income", "Shelter Excess",
                "Excess Shelter Deduction", "Net Income", "Net Income Test",
                "Computed Benefit", "Benefit Amount", "Determination");
    }
}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `./mvnw -pl rules-engine test -Dtest=DmnModelSanityTest`
Expected: FAIL — `SnapDmnEvaluator` does not exist.

- [ ] **Step 3: Author the DMN model**

Create `snap-eligibility.dmn` with `namespace="https://canopica/dmn/snap"` and
`name="snap-eligibility"`, item definitions `tSnapFacts` and
`tSnapParameters` matching the two records, then the fifteen decisions above.
Author it as DMN 1.4 XML by hand; validate by running Step 4's test rather
than by eye.

Two authoring notes that save a debugging cycle:
- Every decision's `variable` element must carry a `typeRef`
  (`number`, `boolean`, `string`) or FEEL will infer `Any` and downstream
  arithmetic silently returns null.
- Decision-table input expressions reference upstream decisions by their
  **variable name**, and each such reference also needs an
  `<informationRequirement>` naming that decision's `href`. A missing
  requirement is the single most common cause of a null input at runtime.

- [ ] **Step 4: Implement the evaluator**

```java
package canopica.rules;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.kie.dmn.api.core.DMNContext;
import org.kie.dmn.api.core.DMNModel;
import org.kie.dmn.api.core.DMNResult;
import org.kie.dmn.api.core.DMNRuntime;
import org.kie.dmn.core.internal.utils.DMNRuntimeBuilder;

public final class SnapDmnEvaluator {

    private static final String NAMESPACE = "https://canopica/dmn/snap";
    private static final String MODEL_NAME = "snap-eligibility";

    private final DMNRuntime runtime;
    private final DMNModel model;

    public SnapDmnEvaluator() {
        this.runtime = DMNRuntimeBuilder.fromDefaults()
                .buildConfiguration()
                .fromClasspathResource("dmn/snap-eligibility.dmn",
                        SnapDmnEvaluator.class.getClassLoader())
                .getOrElseThrow(e -> new DmnEvaluationException("cannot load DMN model", e));
        this.model = runtime.getModel(NAMESPACE, MODEL_NAME);
        if (model == null) {
            throw new DmnEvaluationException(
                    "DMN model " + NAMESPACE + "#" + MODEL_NAME + " not found on the classpath");
        }
    }

    public List<String> modelMessages() {
        return model.getMessages().stream().map(Object::toString).toList();
    }

    public SnapDecision evaluate(SnapFacts facts, SnapPolicyParameters parameters) {
        DMNContext context = runtime.newContext();
        context.set("Facts", asMap(facts));
        context.set("Parameters", asMap(parameters));

        DMNResult result = runtime.evaluateAll(model, context);
        if (result.hasErrors()) {
            throw new DmnEvaluationException("DMN evaluation failed: " + result.getMessages());
        }

        Map<String, Object> trace = new LinkedHashMap<>();
        result.getDecisionResults()
                .forEach(dr -> trace.put(dr.getDecisionName(), dr.getResult()));

        @SuppressWarnings("unchecked")
        Map<String, Object> determination =
                (Map<String, Object>) result.getDecisionResultByName("Determination").getResult();

        return new SnapDecision(
                (Boolean) determination.get("eligible"),
                toMoney(determination.get("benefitAmount")),
                (String) determination.get("reasonCode"),
                Map.copyOf(trace));
    }

    // asMap(...) converts each record to a LinkedHashMap keyed by the field
    // names in the DMN item definitions; toMoney(...) converts FEEL's
    // BigDecimal result to scale 2, HALF_UP.
}
```

If `DMNRuntimeBuilder.fromClasspathResource` does not resolve against the
installed 10.2.0 API, fall back to the `KieServices` route — a `kmodule.xml`
under `src/main/resources/META-INF/` and
`KieServices.Factory.get().getKieClasspathContainer().newKieSession()
.getKieRuntime(DMNRuntime.class)` — and keep the rest of the class
unchanged. Step 1's test is what tells you which one you are on.

- [ ] **Step 5: Run the sanity test and watch it pass**

Run: `./mvnw -pl rules-engine test -Dtest=DmnModelSanityTest` → PASS.

- [ ] **Step 6: Write the table-driven scenario suite**

Every scenario is hand-computed from the published SNAP arithmetic and
asserted exactly. `TestFixtures.fy2025Parameters(size)` builds a
`SnapPolicyParameters` **in the test** from the Task 3 table — the rules
engine has no database, so these are literals, and that is deliberate: the
engine's tests must not silently pass because they read the same seed data
the engine read.

```java
package canopica.rules;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class SnapDmnEvaluatorTest {

    private final SnapDmnEvaluator evaluator = new SnapDmnEvaluator();

    static Stream<Arguments> scenarios() {
        return Stream.of(
            // name, facts, expected eligible, expected benefit, expected reason
            Arguments.of("single adult, no income, receives the full allotment",
                TestFixtures.facts().householdSize(1).build(),
                true, "292", "ELIGIBLE"),

            Arguments.of("three-person working household, capped shelter deduction",
                TestFixtures.facts().householdSize(3).earnedIncome("1500")
                        .shelterCost("800").utilityCost("300").build(),
                true, "649", "ELIGIBLE"),

            Arguments.of("high shelter cost is capped for a household with no elderly member",
                TestFixtures.facts().householdSize(3).earnedIncome("1500")
                        .shelterCost("2000").utilityCost("300").build(),
                true, "682", "ELIGIBLE"),

            Arguments.of("the same household with an elderly member gets an uncapped shelter deduction",
                TestFixtures.facts().householdSize(3).earnedIncome("1500")
                        .shelterCost("2000").utilityCost("300")
                        .hasElderlyOrDisabledMember(true).build(),
                true, "768", "ELIGIBLE"),

            Arguments.of("gross income over the limit is denied before any deduction runs",
                TestFixtures.facts().householdSize(1).unearnedIncome("2000").build(),
                false, "0", "GROSS_INCOME_EXCEEDS_LIMIT"),

            Arguments.of("an elderly household is exempt from the gross test but still fails the net test",
                TestFixtures.facts().householdSize(1).unearnedIncome("2000")
                        .hasElderlyOrDisabledMember(true).build(),
                false, "0", "NET_INCOME_EXCEEDS_LIMIT"),

            Arguments.of("categorical eligibility bypasses both income tests",
                TestFixtures.facts().householdSize(2).unearnedIncome("2500")
                        .categoricallyEligible(true).build(),
                true, "23", "ELIGIBLE"),

            Arguments.of("a one-person household below the minimum receives the minimum benefit",
                TestFixtures.facts().householdSize(1).unearnedIncome("1400").build(),
                true, "23", "ELIGIBLE"),

            Arguments.of("a three-person household computing to zero is denied, not awarded zero",
                TestFixtures.facts().householdSize(3).unearnedIncome("3000")
                        .categoricallyEligible(true).build(),
                false, "0", "ZERO_BENEFIT_AMOUNT")
        );
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("scenarios")
    void evaluatesSnapScenario(String name, SnapFacts facts,
                               boolean expectedEligible, String expectedBenefit,
                               String expectedReason) {
        SnapDecision decision = evaluator.evaluate(
                facts, TestFixtures.fy2025Parameters(facts.householdSize()));

        assertThat(decision.eligible()).isEqualTo(expectedEligible);
        assertThat(decision.benefitAmount()).isEqualByComparingTo(new BigDecimal(expectedBenefit));
        assertThat(decision.reasonCode()).isEqualTo(expectedReason);
    }
}
```

The arithmetic behind two of them, so a reviewer can check the fixtures
rather than trust them:

- *Three-person working household:* gross 1500 ≤ 2798 → PASS. Standard 204,
  earned 20% = 300 → adjusted 996. Shelter 1100 − (50% × 996 = 498) = 602
  excess, under the 712 cap → net 996 − 602 = 394 ≤ 2152 → PASS.
  Benefit 768 − ceiling(394 × 0.30 = 118.2) = 768 − 119 = **649**.
- *Same household, elderly member, shelter 2300:* excess 2300 − 498 = 1802,
  uncapped → net max(0, 996 − 1802) = 0 → benefit 768 − 0 = **768**.

- [ ] **Step 7: Add the as-of-date correctness test**

Required by CLAUDE.md's testing policy. Proves the parameters are genuinely
injected, not baked into the model:

```java
@Test
void thesameFactsProduceDifferentBenefitsUnderDifferentParameterVersions() {
    SnapFacts facts = TestFixtures.facts().householdSize(3).earnedIncome("1500")
            .shelterCost("800").utilityCost("300").build();

    SnapDecision underFy2025 = evaluator.evaluate(facts, TestFixtures.fy2025Parameters(3));
    // A synthetic later version: max allotment 800, standard deduction 210.
    SnapDecision underLater = evaluator.evaluate(facts,
            TestFixtures.parameters(3).versionLabel("SNAP-TEST-LATER")
                    .maxAllotment("800").standardDeduction("210").build());

    assertThat(underFy2025.benefitAmount()).isEqualByComparingTo("649");
    // adjusted 1500-210-300 = 990; shelter excess 1100-495 = 605; net 385;
    // benefit 800 - ceiling(115.5) = 800 - 116 = 684
    assertThat(underLater.benefitAmount()).isEqualByComparingTo("684");
}
```

- [ ] **Step 8: Run the scenario suite**

Run: `./mvnw -pl rules-engine test` → all scenarios PASS. Any mismatch is a
DMN authoring bug (check the `informationRequirement` note in Step 3), not a
reason to change an expected value — the expected values are policy
arithmetic, and changing one to make a test pass is how a rules engine
quietly becomes wrong.

- [ ] **Step 9: Write `rules-engine/README.md` and commit**

The README documents the decision graph table above, the numbers-vs-logic
boundary, and the named out-of-scope items. Then:

```bash
make test && make lint
git add -A && git commit -m "Task 4: SNAP DMN decision model on Drools/KIE with table-driven scenarios"
```

---

## Task 5: Determination service — persisted determination + trace

Assembles facts as of a decision date, resolves the parameter set as of the
same date, evaluates the DMN model, and writes an append-only
`eligibility_determination` plus its complete `determination_trace`.

**Files:**
- Create: `portal/src/main/resources/db/migration/V5__determination.sql`
- Create: `portal/src/main/java/canopica/portal/determination/FactAssembler.java`
- Create: `portal/src/main/java/canopica/portal/determination/DeterminationService.java`
- Create: `portal/src/main/java/canopica/portal/domain/EligibilityDetermination.java`,
  `DeterminationTrace.java`
- Create: `portal/src/main/java/canopica/portal/repo/EligibilityDeterminationRepository.java`,
  `DeterminationTraceRepository.java`
- Create: `portal/src/test/java/canopica/portal/determination/FactAssemblerTest.java`
- Create: `portal/src/test/java/canopica/portal/determination/DeterminationServiceTest.java`
- Create: `portal/src/test/java/canopica/portal/determination/DeterminationReproducibilityTest.java`
- Create: `portal/src/test/java/canopica/portal/CaseFixtures.java` (builds a household with
  members, income, expenses in the database and returns its ids)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: `PolicyParameterResolver` (Task 3), `SnapDmnEvaluator`,
  `SnapFacts`, `SnapDecision` (Task 4), the repositories from Task 2.
- Produces:

```java
public interface DeterminationService {
    /** Evaluates one program request as of a date and appends the result.
     *  @return the id of the new eligibility_determination row. */
    UUID determine(UUID programRequestId, LocalDate asOf, LocalDate benefitMonth, String decidedBy);

    /** Re-evaluates a stored determination against its own recorded parameter
     *  set version and returns the result WITHOUT persisting anything. */
    SnapDecision reproduce(UUID determinationId);
}
```

- [ ] **Step 1: Write `V5__determination.sql`**

```sql
create table eligibility_determination (
    id                      uuid primary key,
    program_request_id      uuid        not null references program_request (id),
    benefit_month           date        not null,
    -- The date the facts and parameters were resolved as of. Not the same as
    -- decided_at: a determination can be made today for a past benefit month.
    as_of_date              date        not null,
    eligible                boolean     not null,
    benefit_amount          numeric(12, 2) not null check (benefit_amount >= 0),
    reason_code             text        not null check (reason_code in
                                ('ELIGIBLE', 'GROSS_INCOME_EXCEEDS_LIMIT',
                                 'NET_INCOME_EXCEEDS_LIMIT', 'ZERO_BENEFIT_AMOUNT')),
    -- The version used, stored as a value, not a pointer to "current".
    policy_parameter_set_id uuid        not null references policy_parameter_set (id),
    policy_parameter_version text       not null,
    decided_at              timestamptz not null default now(),
    decided_by              text        not null,
    constraint eligibility_determination_benefit_month_first check (extract(day from benefit_month) = 1),
    constraint eligibility_determination_eligible_has_benefit
        check ((eligible and benefit_amount > 0) or (not eligible and benefit_amount = 0))
);

create table determination_trace (
    id                      uuid primary key,
    determination_id        uuid        not null unique references eligibility_determination (id),
    -- The exact facts fed to the engine, as of as_of_date.
    input_snapshot          jsonb       not null,
    -- Every named DMN decision's result, in evaluation order.
    decision_results        jsonb       not null,
    dmn_model_name          text        not null,
    -- SHA-256 of the .dmn file the evaluation ran against, so a later
    -- re-derivation can prove it used the same model, not just the same numbers.
    dmn_model_hash          text        not null,
    engine_version          text        not null,
    created_at              timestamptz not null default now()
);

-- Append-only: a changed circumstance produces a NEW determination
-- (roadmap §3.4.1). The database refuses anything else.
create or replace function determination_is_append_only() returns trigger
language plpgsql as $$
begin
    raise exception 'eligibility_determination is append-only (attempted %); '
                    'record a new determination instead', tg_op;
end;
$$;

create trigger eligibility_determination_no_mutation
    before update or delete on eligibility_determination
    for each row execute function determination_is_append_only();

create trigger determination_trace_no_mutation
    before update or delete on determination_trace
    for each row execute function determination_is_append_only();

create index eligibility_determination_request_idx
    on eligibility_determination (program_request_id, benefit_month, decided_at desc);
```

- [ ] **Step 2: Write the failing fact-assembler test**

`FactAssemblerTest` (extends `AbstractPostgresTest`) builds, via
`CaseFixtures`, a three-person household with one wage earner at $1,500/mo
effective 2025-01-01, rent $800 and utilities $300, plus **a second income
record effective 2025-07-01 that must not appear** in an as-of 2025-06-15
assembly. Assertions:

```java
SnapFacts facts = assembler.assemble(householdId, LocalDate.of(2025, 6, 15));

assertThat(facts.householdSize()).isEqualTo(3);
assertThat(facts.earnedIncome()).isEqualByComparingTo("1500");   // not 2100
assertThat(facts.shelterCost()).isEqualByComparingTo("800");
assertThat(facts.utilityCost()).isEqualByComparingTo("300");
assertThat(facts.hasElderlyOrDisabledMember()).isFalse();
```

Plus one test where a member turned 60 before the as-of date and one where a
`disability_record` is effective, both asserting
`hasElderlyOrDisabledMember()` is true — age 60 is computed from
`person.date_of_birth` against `asOf`, not stored as a flag.

- [ ] **Step 3: Run it, watch it fail, then implement `FactAssembler`**

`FactAssembler` reads household members effective on the date, their persons,
their income and expense records effective on the date, and the household's
living arrangement, then maps expense types onto `SnapFacts`:
`RENT_OR_MORTGAGE` + `PROPERTY_TAX` + `HOME_INSURANCE` → `shelterCost`;
`UTILITIES` → `utilityCost`; `DEPENDENT_CARE` → `dependentCareCost`;
`MEDICAL` → `medicalExpense`. `earnedIncome` sums records with
`is_earned = true`, `unearnedIncome` the rest.

Categorical eligibility in Phase 1a is derived from receipt of SSI:
`categoricallyEligible` is true when any member has an effective
`income_record` of type `SSI`. Broad-based categorical eligibility (BBCE)
via TANF-funded services is state-configured and is Phase 1b.

Run: `./mvnw -pl portal test -Dtest=FactAssemblerTest` → PASS.

- [ ] **Step 4: Write the failing determination-service test**

```java
@Test
void persistsADeterminationAndItsCompleteTrace() {
    var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);   // the Task 4 scenario

    UUID determinationId = service.determine(
            ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

    var row = jdbc.queryForMap(
            "select * from eligibility_determination where id = ?", determinationId);
    assertThat(row.get("eligible")).isEqualTo(true);
    assertThat((BigDecimal) row.get("benefit_amount")).isEqualByComparingTo("649");
    assertThat(row.get("policy_parameter_version")).isEqualTo("SNAP-FY2025");

    var trace = jdbc.queryForMap(
            "select * from determination_trace where determination_id = ?", determinationId);
    assertThat(trace.get("dmn_model_hash")).asString().hasSize(64);
    assertThat(trace.get("decision_results").toString())
            .contains("Excess Shelter Deduction", "Net Income", "Benefit Amount");
}

@Test
void refusesToMutateAnExistingDetermination() {
    UUID id = /* … */;
    assertThatThrownBy(() -> jdbc.update(
            "update eligibility_determination set benefit_amount = 1 where id = ?", id))
            .hasMessageContaining("append-only");
}
```

- [ ] **Step 5: Implement `DeterminationService`**

One `@Transactional` method: assemble facts → resolve parameters for
`facts.householdSize()` as of `asOf` → `evaluator.evaluate(...)` → insert the
determination → insert the trace (`input_snapshot` = the `SnapFacts` record
serialized by Jackson; `decision_results` = `decision.trace()`;
`dmn_model_hash` = SHA-256 of the classpath `.dmn` resource, computed once at
bean construction; `engine_version` = the `kie-dmn-core` implementation
version from its package metadata).

`reproduce(determinationId)` loads the stored `input_snapshot`, deserializes
it back into `SnapFacts`, re-resolves parameters **by the stored
`policy_parameter_set_id`** rather than by date, and re-evaluates. It
persists nothing.

Run: `./mvnw -pl portal test -Dtest=DeterminationServiceTest` → PASS.

- [ ] **Step 6: Write the reproducibility test — the one CLAUDE.md names explicitly**

```java
class DeterminationReproducibilityTest extends AbstractPostgresTest {

    @Test
    void anOldDeterminationReRunAgainstItsOwnParameterVersionProducesItsOriginalAnswer() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID original = service.determine(ids.programRequestId(),
                LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        // Time moves on: a new fiscal year is in force and the household's
        // income has since changed. Neither may affect the stored decision.
        CaseFixtures.reportIncomeChange(jdbc, ids, "2600", LocalDate.of(2025, 11, 1));

        SnapDecision reproduced = service.reproduce(original);

        assertThat(reproduced.benefitAmount()).isEqualByComparingTo("649");
        assertThat(reproduced.reasonCode()).isEqualTo("ELIGIBLE");
    }

    @Test
    void aDeterminationMadeAfterOctoberFirstUsesTheNewFiscalYearsParameters() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID later = service.determine(ids.programRequestId(),
                LocalDate.of(2025, 11, 15), LocalDate.of(2025, 11, 1), "SYSTEM");
        assertThat(jdbc.queryForObject(
                "select policy_parameter_version from eligibility_determination where id = ?",
                String.class, later)).isEqualTo("SNAP-FY2026");
    }
}
```

- [ ] **Step 7: Run the full suite and commit**

```bash
make test && make lint
git add -A && git commit -m "Task 5: determination service with persisted DMN trace and as-of reproducibility"
```

---

## Task 6: Hash-chained audit log + CI verification job

Turns "immutable audit log" from a claim into a control a reader can verify
(roadmap §3.6). Three layers, each independently tested: the chain is
computed **by the database** so the application cannot forge it; `UPDATE` and
`DELETE` are revoked from the application role *and* blocked by trigger; a
verifier walks the chain and CI fails the build if it does not hold.

**Files:**
- Create: `portal/src/main/resources/db/migration/V6__audit_event.sql`
- Create: `portal/src/main/java/canopica/portal/audit/AuditService.java`,
  `AuditEventType.java`
- Create: `portal/src/test/java/canopica/portal/audit/AuditChainTest.java`
- Create: `data-platform/src/canopica_data/audit/verify_chain.py`
- Create: `data-platform/tests/test_verify_chain.py` (integration)
- Create: `data-platform/tests/conftest.py` (Postgres container fixture)
- Modify: `portal/src/main/java/canopica/portal/determination/DeterminationService.java`
  (append an audit event per determination), `.github/workflows/ci.yml`,
  `docs/STATUS.md`

**Interfaces:**
- Consumes: Task 5's determination flow.
- Produces:

```java
public interface AuditService {
    /** Appends one audit event. The chain hash is assigned by the database. */
    void append(AuditEventType type, String actorId, String subjectType,
                UUID subjectId, Map<String, Object> payload);
}
```

```python
def verify_chain(dsn: str) -> ChainVerification:
    """Recompute every audit_event hash in id order and compare.

    Returns ChainVerification(rows_checked: int, ok: bool, first_bad_id: int | None).
    """
```

- [ ] **Step 1: Write `V6__audit_event.sql`**

```sql
create extension if not exists pgcrypto;

create table audit_event (
    id              bigserial primary key,
    occurred_at     timestamptz not null default now(),
    event_type      text        not null check (event_type in
                        ('APPLICATION_SUBMITTED', 'DETERMINATION_MADE',
                         'CASE_VIEWED', 'VERIFICATION_UPDATED')),
    actor_id        text        not null,
    subject_type    text        not null,
    subject_id      uuid        not null,
    payload         jsonb       not null,
    prev_hash       char(64)    not null,
    hash            char(64)    not null
);

-- The chain is computed in the database, in a trigger, under a transaction-
-- scoped advisory lock. The application supplies the payload and nothing
-- else: it cannot choose, skip, or backdate a hash.
--
-- jsonb::text is canonical in Postgres (keys sorted, whitespace normalized),
-- so the hashed string is stable across clients and drivers.
create or replace function audit_event_chain() returns trigger
language plpgsql as $$
declare
    last_hash char(64);
    material  text;
begin
    perform pg_advisory_xact_lock(hashtext('canopica.audit_event'));

    select hash into last_hash from audit_event order by id desc limit 1;
    new.prev_hash := coalesce(last_hash, repeat('0', 64));

    material := new.prev_hash
        || to_char(new.occurred_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.USOF')
        || new.event_type || new.actor_id || new.subject_type
        || new.subject_id::text || new.payload::text;

    new.hash := encode(digest(material, 'sha256'), 'hex');
    return new;
end;
$$;

create trigger audit_event_chain_before_insert
    before insert on audit_event
    for each row execute function audit_event_chain();

create or replace function audit_event_is_append_only() returns trigger
language plpgsql as $$
begin
    raise exception 'audit_event is append-only (attempted %)', tg_op;
end;
$$;

create trigger audit_event_no_mutation
    before update or delete on audit_event
    for each row execute function audit_event_is_append_only();

-- Defence in depth: the trigger stops the owner; the grant stops everyone
-- else. Flyway substitutes ${app_role} from spring.flyway.placeholders.
revoke update, delete on audit_event from public;
revoke update, delete on audit_event from ${app_role};
grant insert, select on audit_event to ${app_role};

create index audit_event_subject_idx on audit_event (subject_type, subject_id);
```

Set `spring.flyway.placeholders.app_role: ${CANOPICA_OPERATIONAL_USER:canopica_app}` in
`application.yml`.

- [ ] **Step 2: Write the failing chain test**

```java
class AuditChainTest extends AbstractPostgresTest {

    @Autowired AuditService audit;
    @Autowired JdbcTemplate jdbc;

    @Test
    void firstEventChainsFromTheZeroHash() {
        audit.append(AuditEventType.CASE_VIEWED, "worker-1", "household", UUID.randomUUID(), Map.of());
        assertThat(jdbc.queryForObject(
                "select prev_hash from audit_event order by id limit 1", String.class))
                .isEqualTo("0".repeat(64));
    }

    @Test
    void eachEventChainsFromItsPredecessor() {
        for (int i = 0; i < 5; i++) {
            audit.append(AuditEventType.CASE_VIEWED, "worker-1", "household",
                    UUID.randomUUID(), Map.of("seq", i));
        }
        var rows = jdbc.queryForList("select id, prev_hash, hash from audit_event order by id");
        for (int i = 1; i < rows.size(); i++) {
            assertThat(rows.get(i).get("prev_hash")).isEqualTo(rows.get(i - 1).get("hash"));
        }
    }

    @Test
    void refusesUpdateAndDelete() {
        audit.append(AuditEventType.CASE_VIEWED, "worker-1", "household", UUID.randomUUID(), Map.of());
        assertThatThrownBy(() -> jdbc.update("update audit_event set actor_id = 'x'"))
                .hasMessageContaining("append-only");
        assertThatThrownBy(() -> jdbc.update("delete from audit_event"))
                .hasMessageContaining("append-only");
    }

    @Test
    void everyDeterminationAppendsExactlyOneAuditEvent() {
        var ids = CaseFixtures.threePersonWorkingHousehold(jdbc);
        UUID determinationId = determinationService.determine(
                ids.programRequestId(), LocalDate.of(2025, 6, 15), LocalDate.of(2025, 6, 1), "SYSTEM");

        var events = jdbc.queryForList(
                "select event_type, subject_id, payload from audit_event "
                        + "where event_type = 'DETERMINATION_MADE'");
        assertThat(events).hasSize(1);
        assertThat(events.get(0).get("subject_id")).isEqualTo(determinationId);
    }
}
```

- [ ] **Step 3: Run it, watch it fail, implement `AuditService` and wire it into `DeterminationService`**

`AuditService` is a thin JDBC insert (`insert into audit_event (event_type,
actor_id, subject_type, subject_id, payload) values (?, ?, ?, ?, ?::jsonb)`)
— it deliberately does not set `prev_hash` or `hash`. `DeterminationService`
appends a `DETERMINATION_MADE` event inside the same transaction as the
determination insert, with a payload of
`{eligible, benefitAmount, reasonCode, policyParameterVersion, asOfDate}`.

Run: `./mvnw -pl portal test -Dtest=AuditChainTest` → PASS.

- [ ] **Step 4: Write the Python verifier's failing test**

`data-platform/tests/conftest.py` provides a session-scoped Postgres
container fixture (`uv add --dev testcontainers`) that applies the portal's
Flyway migrations by running `flyway` from the
`flyway/flyway:11-alpine` image against it — one fixture, reused by every
Python integration test in this repo.

```python
import pytest

from canopica_data.audit.verify_chain import verify_chain


@pytest.mark.integration
def test_verifies_an_untampered_chain(seeded_audit_dsn: str) -> None:
    result = verify_chain(seeded_audit_dsn)
    assert result.ok
    assert result.rows_checked == 5
    assert result.first_bad_id is None


@pytest.mark.integration
def test_detects_a_tampered_payload(seeded_audit_dsn: str, as_superuser) -> None:
    # Only a superuser can do this — which is the point: the control detects
    # what it cannot prevent.
    as_superuser("alter table audit_event disable trigger audit_event_no_mutation")
    as_superuser("update audit_event set payload = '{\"tampered\": true}'::jsonb where id = 3")

    result = verify_chain(seeded_audit_dsn)
    assert not result.ok
    assert result.first_bad_id == 3
```

- [ ] **Step 5: Implement `verify_chain.py`**

```python
"""Walk the audit chain and recompute every hash.

Run standalone in CI:  uv run python -m canopica_data.audit.verify_chain --dsn "$CANOPICA_OPERATIONAL_DSN"
Exit code 1 on a broken chain, so a workflow step fails the build.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass

import psycopg

ZERO_HASH = "0" * 64


@dataclass(frozen=True)
class ChainVerification:
    rows_checked: int
    ok: bool
    first_bad_id: int | None


def verify_chain(dsn: str) -> ChainVerification:
    previous = ZERO_HASH
    checked = 0
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        # The database does the canonicalization: same to_char format and
        # same jsonb::text the trigger used, so this verifier and the trigger
        # cannot disagree about formatting, only about content.
        cur.execute(
            """
            select id, prev_hash, hash,
                   to_char(occurred_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.USOF')
                     || event_type || actor_id || subject_type
                     || subject_id::text || payload::text as tail
            from audit_event
            order by id
            """
        )
        for row_id, prev_hash, stored_hash, tail in cur:
            expected = hashlib.sha256((previous + tail).encode("utf-8")).hexdigest()
            if prev_hash != previous or stored_hash != expected:
                return ChainVerification(checked, False, row_id)
            previous = stored_hash
            checked += 1
    return ChainVerification(checked, True, None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Canopica audit hash chain.")
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    result = verify_chain(args.dsn)
    print(f"audit chain: {result.rows_checked} rows checked, ok={result.ok}")
    if not result.ok:
        print(f"chain broken at audit_event.id = {result.first_bad_id}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `uv run pytest -m integration tests/test_verify_chain.py` → PASS.

- [ ] **Step 6: Add the CI job**

Append to `.github/workflows/ci.yml`:

```yaml
  audit-chain:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: data-platform } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true }
      - run: uv sync --dev
      - run: uv run pytest -m integration tests/test_verify_chain.py
```

- [ ] **Step 7: Run the full suite and commit**

```bash
make test && make lint && cd data-platform && uv run pytest -m integration
git add -A && git commit -m "Task 6: hash-chained append-only audit log with CI chain verification"
```

---

## Task 7: Portal API — intake + worker case view

Roles are hardcoded in Phase 1a (no Keycloak until 1b), but they are
hardcoded *behind Spring Security's normal abstractions*, so Phase 1b swaps
one filter and nothing else.

**Files:**
- Create: `portal/src/main/java/canopica/portal/api/IntakeController.java`,
  `DeterminationController.java`, `WorkerCaseController.java`
- Create: `portal/src/main/java/canopica/portal/api/dto/` — `IntakeRequest`,
  `IntakePersonDto`, `IntakeIncomeDto`, `IntakeExpenseDto`, `IntakeResponse`,
  `DetermineRequest`, `DeterminationResponse`, `CaseSummaryResponse`,
  `CaseDetailResponse`, `TraceResponse`
- Create: `portal/src/main/java/canopica/portal/intake/IntakeService.java`
- Create: `portal/src/main/java/canopica/portal/config/SecurityConfig.java`,
  `HardcodedRoleFilter.java`
- Create: `portal/src/main/java/canopica/portal/api/ApiExceptionHandler.java`
- Create: `portal/src/test/java/canopica/portal/api/IntakeControllerTest.java`,
  `WorkerCaseControllerTest.java`, `AuthorizationTest.java`
- Create: `portal/src/test/java/canopica/portal/api/TestPayloads.java` (intake JSON
  string constants: a valid three-person working household, one with no
  members, one with inverted effective dates)
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: `DeterminationService`, `AuditService`, Task 2 repositories.
- Produces the HTTP contract Task 8's client and Task 13's e2e test both use:

| Method | Path | Role | Body / Response |
|---|---|---|---|
| `POST` | `/api/applications` | CUSTOMER | `IntakeRequest` → `201` + `IntakeResponse {applicationId, programRequestId}` |
| `POST` | `/api/program-requests/{id}/determinations` | WORKER | `DetermineRequest {asOfDate, benefitMonth}` → `201` + `DeterminationResponse` |
| `GET` | `/api/program-requests/{id}` | WORKER | `CaseDetailResponse` |
| `GET` | `/api/worker/cases` | WORKER | `CaseSummaryResponse[]` |
| `GET` | `/api/determinations/{id}/trace` | WORKER | `TraceResponse {inputSnapshot, decisionResults, dmnModelHash, policyParameterVersion}` |
| `GET` | `/actuator/health` | – | Compose healthcheck |

```java
public record DeterminationResponse(
        UUID determinationId, boolean eligible, BigDecimal benefitAmount,
        String reasonCode, String policyParameterVersion,
        LocalDate benefitMonth, LocalDate asOfDate, Instant decidedAt) {}
```

- [ ] **Step 1: Write the failing intake contract test**

```java
class IntakeControllerTest extends AbstractPostgresTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;

    @Test
    void submittingAnApplicationCreatesAProgramRequestAndAnAuditEvent() throws Exception {
        String body = TestPayloads.threePersonWorkingHouseholdIntake();  // JSON string constant

        String response = mvc.perform(post("/api/applications")
                        .header("X-Canopica-Role", "CUSTOMER")
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.programRequestId").isNotEmpty())
                .andReturn().getResponse().getContentAsString();

        assertThat(jdbc.queryForObject(
                "select count(*) from program_request where program_code = 'SNAP'", Integer.class))
                .isEqualTo(1);
        assertThat(jdbc.queryForObject(
                "select count(*) from audit_event where event_type = 'APPLICATION_SUBMITTED'",
                Integer.class)).isEqualTo(1);
    }

    @Test
    void rejectsAnIntakeWithNoHouseholdMembers() throws Exception {
        mvc.perform(post("/api/applications").header("X-Canopica-Role", "CUSTOMER")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(TestPayloads.intakeWithNoMembers()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value("members"));
    }

    @Test
    void rejectsAnIntakeWhoseEffectiveDatesAreInverted() throws Exception {
        mvc.perform(post("/api/applications").header("X-Canopica-Role", "CUSTOMER")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(TestPayloads.intakeWithInvertedIncomeDates()))
                .andExpect(status().isBadRequest());
    }
}
```

`AuthorizationTest` asserts a `CUSTOMER` role gets `403` from
`/api/worker/cases` and from the determination endpoint, and that a missing
`X-Canopica-Role` header gets `401`.

- [ ] **Step 2: Run it and watch it fail; then implement**

`SecurityConfig` uses Spring Security's normal `SecurityFilterChain` with
`authorizeHttpRequests` mapping `/api/worker/**` and the determination
endpoint to `hasRole("WORKER")`, and registers `HardcodedRoleFilter` before
`UsernamePasswordAuthenticationFilter`. The filter reads `X-Canopica-Role`,
rejects an unknown or missing value with `401`, and sets a
`UsernamePasswordAuthenticationToken` with `ROLE_CUSTOMER` or `ROLE_WORKER`.
It carries a class-level comment naming Phase 1b as its replacement, so
nobody mistakes it for a finished auth story.

Bean-validation annotations on the DTOs (`@NotEmpty` on `members`,
`@PositiveOrZero` on amounts, a class-level `@EffectiveRange` constraint
checking `effectiveTo >= effectiveFrom`) drive the `400`s;
`ApiExceptionHandler` maps `MethodArgumentNotValidException` to
`{errors: [{field, message}]}` and `PolicyParameterNotFoundException` to
`422` with a clear message.

`IntakeService` writes person → household → household_member →
living_arrangement → income/expense records → application → program_request
in one transaction, then appends the `APPLICATION_SUBMITTED` audit event.

Run: `./mvnw -pl portal test -Dtest=IntakeControllerTest,AuthorizationTest` → PASS.

- [ ] **Step 3: Write and pass the worker-view tests**

`WorkerCaseControllerTest` asserts: the case list returns one row per program
request with household head name, status, submitted date, and latest
determination summary; the detail endpoint returns the determination history
newest-first (proving append-only produces history, not overwrites); viewing
a case appends a `CASE_VIEWED` audit event (this is the row-level-access
evidence Phase 1b's `mart_access_review` reports on); and the trace endpoint
returns the same decision names the DMN model defines.

- [ ] **Step 4: Run the full suite and commit**

```bash
make test && make lint
git add -A && git commit -m "Task 7: intake and worker case-view API with hardcoded roles"
```

---

## Task 8: React UI — intake form + worker case view

One React app, role-gated views (the deliberate simplification recorded in
the Phase 1 doc §8). Vitest + React Testing Library; queries go through
accessible roles and labels, which makes Phase 1b's Section 508 work an
extension rather than a rewrite.

**Files:**
- Create: `portal/web/src/api/client.ts`, `portal/web/src/api/types.ts`
- Create: `portal/web/src/App.tsx` (router + role switch), `src/RoleContext.tsx`
- Create: `portal/web/src/pages/IntakePage.tsx`, `WorkerCasesPage.tsx`, `CaseDetailPage.tsx`
- Create: `portal/web/src/components/HouseholdMemberFields.tsx`,
  `IncomeFields.tsx`, `ExpenseFields.tsx`, `DeterminationPanel.tsx`, `TracePanel.tsx`
- Create: `portal/web/src/pages/IntakePage.test.tsx`,
  `WorkerCasesPage.test.tsx`, `CaseDetailPage.test.tsx`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: Task 7's HTTP contract.
- Produces: `src/api/types.ts` — TypeScript mirrors of the Java DTOs, hand-written
  and kept in sync by Task 13's e2e test, which fails if a field disappears.

```ts
export type DeterminationResponse = {
  determinationId: string;
  eligible: boolean;
  benefitAmount: string;      // string, not number: money never round-trips through a float
  reasonCode: 'ELIGIBLE' | 'GROSS_INCOME_EXCEEDS_LIMIT'
            | 'NET_INCOME_EXCEEDS_LIMIT' | 'ZERO_BENEFIT_AMOUNT';
  policyParameterVersion: string;
  benefitMonth: string; asOfDate: string; decidedAt: string;
};
```

- [ ] **Step 1: Write the failing intake-page test**

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import * as client from '../api/client';
import IntakePage from './IntakePage';

test('submits a household and shows the confirmation with its request id', async () => {
  const submit = vi.spyOn(client, 'submitApplication').mockResolvedValue({
    applicationId: 'a-1', programRequestId: 'pr-1',
  });

  render(<IntakePage />);
  await userEvent.type(screen.getByLabelText(/first name/i), 'Dana');
  await userEvent.type(screen.getByLabelText(/last name/i), 'Reyes');
  await userEvent.type(screen.getByLabelText(/date of birth/i), '1990-04-02');
  await userEvent.type(screen.getByLabelText(/monthly earned income/i), '1500');
  await userEvent.type(screen.getByLabelText(/monthly rent or mortgage/i), '800');
  await userEvent.click(screen.getByRole('button', { name: /submit application/i }));

  await waitFor(() => expect(submit).toHaveBeenCalledOnce());
  expect(await screen.findByText(/pr-1/)).toBeInTheDocument();
});

test('shows a field-level error when the API rejects the submission', async () => {
  vi.spyOn(client, 'submitApplication').mockRejectedValue(
    new client.ApiValidationError([{ field: 'members', message: 'must not be empty' }]));

  render(<IntakePage />);
  await userEvent.click(screen.getByRole('button', { name: /submit application/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(/must not be empty/i);
});
```

- [ ] **Step 2: Run it, watch it fail, implement `IntakePage` + `client.ts`**

`client.ts` wraps `fetch` with the `X-Canopica-Role` header from `RoleContext`,
parses the `{errors: [...]}` body into `ApiValidationError`, and exposes
`submitApplication`, `listCases`, `getCase`, `runDetermination`, `getTrace`.
Every form control has an explicit `<label htmlFor>`; errors render in a
`role="alert"` region.

Run: `npm test -- IntakePage` → PASS.

- [ ] **Step 3: Write and pass the worker-view tests**

`WorkerCasesPage.test.tsx`: renders a table of cases from a mocked
`listCases`, with a link per row; asserts the table has an accessible name
and column headers. `CaseDetailPage.test.tsx`: renders the determination
panel (outcome, benefit amount, reason code, **the policy parameter version
in force**), a "Run determination" button that calls `runDetermination` and
re-renders with the new result, and a collapsible trace panel listing each
DMN decision name and value in evaluation order.

The trace panel is the whole point of the persisted trace being a Phase 1a
deliverable: a worker can see *why*, step by step, before any AI exists to
narrate it.

- [ ] **Step 4: Run the full suite and commit**

```bash
npm run typecheck && npm test && cd ../.. && make test
git add -A && git commit -m "Task 8: React intake form, worker case list, and determination trace view"
```

---

## Task 9: Synthetic applicant generator (ACS PUMS–driven)

Every applicant in this repo is synthetic; this is the code that makes that
true and defensible. Distributions come from public ACS PUMS microdata, and
the generator is seeded so any figure in any report is reproducible.

**Files:**
- Create: `data-platform/src/canopica_data/synthetic/__init__.py`, `models.py`,
  `distributions.py`, `generator.py`, `loader.py`, `fetch_pums.py`, `cli.py`
- Create: `data-platform/src/canopica_data/synthetic/data/acs_pums_marginals.json`
- Create: `data-platform/tests/test_generator.py`, `test_loader.py`
- Create: `docs/design/synthetic-data-methodology.md`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: Task 7's `POST /api/applications` contract.
- Produces:

```python
class SyntheticHousehold(BaseModel):
    """One generated household, shaped exactly like the intake API's payload."""
    household_id: uuid.UUID
    county: str
    members: list[SyntheticPerson]
    incomes: list[SyntheticIncome]
    expenses: list[SyntheticExpense]
    living_arrangement: LivingArrangement

def generate_households(count: int, *, seed: int) -> list[SyntheticHousehold]: ...
class IntakeIds(BaseModel):
    application_id: uuid.UUID
    program_request_id: uuid.UUID

def post_households(households: Iterable[SyntheticHousehold], base_url: str) -> list[IntakeIds]: ...
```

- [ ] **Step 1: Establish the distributions and their provenance**

`fetch_pums.py` downloads one state-year ACS PUMS person + household file
from the Census Bureau's public FTP endpoint, computes the marginal
distributions the generator needs, and writes
`data/acs_pums_marginals.json`. It is **not** run at test time or build time
— the computed marginals are committed, so a clone with no network still
generates data, and the fetch script exists so a reader can re-derive them.

Marginals to compute and commit: household size; age by household role;
sex; disability status by age band; employment status by age band; monthly
earned income (deciles, conditional on employment); monthly unearned income
(deciles); monthly rent/mortgage (deciles); utility cost (deciles).

`docs/design/synthetic-data-methodology.md` records the source file, the
vintage, the variables used (`NP`, `AGEP`, `SEX`, `DIS`, `ESR`, `WAGP`,
`SEMP`, `RETP`, `SSIP`, `GRNTP`, `SMOCP`, `ELEP`…), the transformation to
monthly amounts, and the honest limitation — sampling marginals
independently reproduces each variable's distribution but not the full joint
structure, which is a real, stated bound on what any fairness measurement
over this data can claim (roadmap §8, trade-offs doc §4.9).

- [ ] **Step 2: Write the failing generator tests**

```python
def test_generation_is_reproducible_for_a_given_seed() -> None:
    first = generate_households(50, seed=42)
    second = generate_households(50, seed=42)
    assert [h.model_dump_json() for h in first] == [h.model_dump_json() for h in second]


def test_different_seeds_produce_different_households() -> None:
    assert generate_households(50, seed=1) != generate_households(50, seed=2)


def test_household_size_distribution_matches_the_pums_marginal() -> None:
    households = generate_households(5_000, seed=7)
    observed = Counter(len(h.members) for h in households)
    expected = load_marginals()["household_size"]
    for size, share in expected.items():
        assert observed[int(size)] / 5_000 == pytest.approx(share, abs=0.02)


def test_every_household_is_internally_consistent() -> None:
    for household in generate_households(500, seed=3):
        assert len(household.members) >= 1
        assert sum(m.relationship == "SELF" for m in household.members) == 1
        assert all(i.monthly_amount >= 0 for i in household.incomes)
        # Income belongs to a member of this household, not a stranger.
        member_ids = {m.person_id for m in household.members}
        assert all(i.person_id in member_ids for i in household.incomes)
        # Only working-age members have earned income.
        earners = {i.person_id for i in household.incomes if i.is_earned}
        ages = {m.person_id: m.age for m in household.members}
        assert all(ages[p] >= 16 for p in earners)


def test_generated_payload_validates_against_the_intake_contract() -> None:
    # The generator's output IS the API payload; a drift here breaks Task 13.
    payload = generate_households(1, seed=11)[0].to_intake_payload()
    assert set(payload) == {"county", "members", "incomes", "expenses", "livingArrangement"}
```

- [ ] **Step 3: Implement `distributions.py`, `models.py`, `generator.py`**

`generator.py` uses `numpy.random.default_rng(seed)` (add `numpy` — it comes
with Polars-adjacent work anyway and is the right tool for seeded sampling)
and samples: household size → per-member ages and relationships → sex →
disability → employment → income → expenses → living arrangement. Every
sampling call draws from the one `rng` instance so the seed governs
everything.

Run: `uv run pytest tests/test_generator.py` → PASS.

- [ ] **Step 4: Implement the loader and CLI**

`loader.py` posts each household to `POST /api/applications` with
`X-Canopica-Role: CUSTOMER` — deliberately through the real API, not straight into
Postgres, so generated data passes exactly the validation real intake does.
It retries once on a connection error and raises on any `4xx`.

```bash
uv run python -m canopica_data.synthetic.cli generate --count 500 --seed 42 --out households.jsonl
uv run python -m canopica_data.synthetic.cli load --input households.jsonl --api http://localhost:8080
```

`test_loader.py` asserts the posted body matches the intake contract, using a
stubbed transport (`httpx.MockTransport`) — no live server in unit tests.

- [ ] **Step 5: Run the full suite and commit**

```bash
uv run pytest && uv run ruff check . && uv run mypy src tests && cd .. && make test
git add -A && git commit -m "Task 9: seeded ACS PUMS-driven synthetic applicant generator and loader"
```

---

## Task 10: Ingestion + one dbt path through bronze → silver → gold

The medallion path, narrow but real: Delta Lake bronze written by Python,
DuckDB-backed dbt silver and gold, with tests on every model. Widening it to
all of roadmap §3.4.2's tables is Phase 1b; the shape established here is
what gets widened.

**Storage note:** bronze Delta tables live on the local filesystem under
`data-platform/warehouse/bronze/` in Phase 1a. MinIO (the S3-compatible
stand-in) arrives in Phase 1b and is a `storage_options` argument to
`write_deltalake` plus a path prefix change — no model or pipeline rewrite.
Stated here so the local path is not mistaken for a design position.

**Files:**
- Create: `data-platform/src/canopica_data/ingestion/__init__.py`, `extract.py`, `cli.py`
- Create: `data-platform/dbt/canopica_warehouse/dbt_project.yml`, `profiles.yml`, `packages.yml`
- Create: `models/bronze/sources.yml`
- Create: `models/silver/dim_person.sql`, `dim_household.sql`,
  `dim_policy_parameter_set.sql`, `fct_program_request.sql`,
  `fct_eligibility_determination.sql`, `silver.yml`
- Create: `models/gold/mart_determination_outcomes.sql`, `gold.yml`
- Create: `macros/is_pii_column.sql`, `tests/generic/test_no_pii_in_gold.sql`
- Create: `data-platform/tests/test_extract.py`, `test_dbt_build.py`
- Modify: `.github/workflows/ci.yml`, `docs/STATUS.md`

**Interfaces:**
- Consumes: the operational tables from Tasks 2–6.
- Produces:

```python
def extract_to_bronze(dsn: str, bronze_root: Path, tables: Sequence[str],
                      *, batch_id: uuid.UUID | None = None) -> dict[str, int]:
    """Land each operational table as an append-only Delta table.
    Returns {table_name: rows_written}."""
```

and the gold contract Task 11 reads:
`mart_determination_outcomes(benefit_month, program_code, outcome, reason_code,
policy_parameter_version, determination_count, eligible_count,
total_benefit_amount, average_benefit_amount)`.

- [ ] **Step 1: Write the failing extract test**

```python
@pytest.mark.integration
def test_extract_lands_every_row_with_ingest_metadata(seeded_operational_dsn, tmp_path) -> None:
    counts = extract_to_bronze(seeded_operational_dsn, tmp_path,
                               ["person", "eligibility_determination"])
    assert counts["eligibility_determination"] == 1

    table = DeltaTable(str(tmp_path / "eligibility_determination")).to_pyarrow_table()
    assert {"_ingested_at", "_source_table", "_batch_id"} <= set(table.column_names)


@pytest.mark.integration
def test_extract_appends_rather_than_overwrites(seeded_operational_dsn, tmp_path) -> None:
    extract_to_bronze(seeded_operational_dsn, tmp_path, ["person"])
    extract_to_bronze(seeded_operational_dsn, tmp_path, ["person"])
    dt = DeltaTable(str(tmp_path / "person"))
    assert dt.version() == 1                       # two commits, second is version 1
    assert dt.to_pyarrow_table().num_rows == 2 * expected_person_count
```

Bronze is *append-only landings with ingest metadata, no reshaping*
(roadmap §3.4.2) — duplicates across batches are expected and are silver's
problem, which is exactly why silver deduplicates on the natural key and the
latest `_ingested_at`.

- [ ] **Step 2: Implement `extract.py`, run the tests to green**

Read each table with `polars.read_database_uri`, add `_ingested_at`
(UTC now), `_source_table`, `_batch_id`, then
`deltalake.write_deltalake(path, df.to_arrow(), mode="append")`.

- [ ] **Step 3: Configure the dbt project**

`profiles.yml` (committed, no secrets — DuckDB is a local file):

```yaml
canopica_warehouse:
  target: local
  outputs:
    local:
      type: duckdb
      path: "{{ env_var('CANOPICA_DUCKDB_PATH', 'data-platform/warehouse/canopica.duckdb') }}"
      extensions: [delta]
      threads: 4
```

`models/bronze/sources.yml` points each source at its Delta table so dbt
reads the same bytes a lakehouse would:

```yaml
version: 2
sources:
  - name: bronze
    meta:
      external_location: "delta_scan('{{ env_var('CANOPICA_WAREHOUSE_ROOT', 'data-platform/warehouse') }}/bronze/{name}')"
    tables:
      - name: person
      - name: household
      - name: household_member
      - name: program_request
      - name: eligibility_determination
      - name: policy_parameter_set
      - name: policy_parameter
```

- [ ] **Step 4: Write the silver models**

`dim_person.sql` — deduplicate to the latest landing per `id`, and **classify
and tokenize here, not later**: the model selects `ssn_token`, a
`person_key` surrogate, `date_of_birth` truncated to `birth_year`, and
`sha256(lower(first_name || '|' || last_name))` as `name_hash`. Raw names and
full dates of birth stop at silver and never reach gold.

```sql
{{ config(materialized='table') }}

with latest as (
    select *, row_number() over (partition by id order by _ingested_at desc) as rn
    from {{ source('bronze', 'person') }}
)
select
    id                                            as person_key,
    ssn_token,
    extract(year from date_of_birth)::int         as birth_year,
    sex,
    is_us_citizen,
    sha256(lower(first_name || '|' || last_name)) as name_hash,
    _ingested_at                                  as loaded_at
from latest
where rn = 1
```

`dim_policy_parameter_set.sql` — SCD Type 2, sourced from data that is
already effective-dated, which is why this dimension is trivial here and
would not be if the operational model had stored only "current":

```sql
select
    id                       as parameter_set_key,
    version_label,
    program_code,
    effective_from           as valid_from,
    coalesce(effective_to, date '9999-12-31') as valid_to,
    effective_to is null     as is_current,
    source_citation
from {{ source('bronze', 'policy_parameter_set') }}
qualify row_number() over (partition by id order by _ingested_at desc) = 1
```

`fct_eligibility_determination.sql` carries the parameter-set key as a
foreign key to that SCD-2 dimension — this is what lets a report say "under
the rules in force at the time" instead of silently re-scoring history
(roadmap §3.4.2).

- [ ] **Step 5: Write the gold mart**

```sql
{{ config(materialized='table') }}

select
    d.benefit_month,
    r.program_code,
    case when d.eligible then 'ELIGIBLE' else 'DENIED' end as outcome,
    d.reason_code,
    p.version_label            as policy_parameter_version,
    count(*)                   as determination_count,
    count(*) filter (where d.eligible) as eligible_count,
    sum(d.benefit_amount)      as total_benefit_amount,
    round(avg(d.benefit_amount), 2) as average_benefit_amount
from {{ ref('fct_eligibility_determination') }} d
join {{ ref('fct_program_request') }} r on r.program_request_key = d.program_request_key
join {{ ref('dim_policy_parameter_set') }} p on p.parameter_set_key = d.parameter_set_key
group by 1, 2, 3, 4, 5
```

- [ ] **Step 6: Write the tests — schema tests and the PII gate**

`silver.yml` / `gold.yml` carry `not_null` and `unique` on every key,
`relationships` on every foreign key, and `accepted_values` on
`reason_code`, `outcome`, `program_code`, and `status`. Column-level
`meta: {classification: ...}` tags (`PII`, `SENSITIVE`, `PUBLIC`) go on every
silver column — the classification Phase 1b's governance mapping formalizes
starts here rather than being retrofitted.

The custom gate, applied to every gold model:

```sql
-- tests/generic/test_no_pii_in_gold.sql
-- Fails if a gold model exposes a column whose name matches a PII shape.
-- A name-based check is deliberately blunt: it cannot be argued with, and a
-- deliberate exception has to be written down rather than reasoned around.
{% test no_pii_in_gold(model) %}
    with offending as (
        select column_name
        from information_schema.columns
        where table_name = '{{ model.identifier }}'
          and (lower(column_name) similar to
               '%(ssn|social_security|first_name|last_name|full_name|email|phone|date_of_birth|dob|street|address)%')
    )
    select * from offending
{% endtest %}
```

- [ ] **Step 7: Run the pipeline end to end locally**

```bash
uv run python -m canopica_data.ingestion.cli --tables all
cd dbt/canopica_warehouse && uv run dbt build      # runs models AND tests
```
Expected: every model builds; every test passes, including `no_pii_in_gold`.

`test_dbt_build.py` shells out to `dbt build --target local` against a
fixture warehouse and asserts a zero exit code plus the presence of the gold
table, so the pipeline is covered by pytest too and not only by a human
running dbt.

- [ ] **Step 8: Add the CI job and commit**

```yaml
  dbt:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: data-platform } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --dev
      - run: uv run pytest -m integration tests/test_extract.py tests/test_dbt_build.py
```

```bash
git add -A && git commit -m "Task 10: Delta bronze ingestion and dbt silver/gold with schema and PII tests"
```

---

## Task 11: Reporting — serving layer, Metabase, TMDL semantic model

**Files:**
- Create: `data-platform/src/canopica_data/serving/materialize.py`, `cli.py`
- Create: `data-platform/src/canopica_data/reporting/provision_metabase.py`
- Create: `reporting/semantic-model/canopica.tmdl`, `tables/mart_determination_outcomes.tmdl`,
  `README.md`
- Create: `reporting/dashboard/README.md`, `reporting/powerbi/README.md`
- Create: `data-platform/tests/test_materialize.py`, `test_semantic_model.py`
- Modify: `infra/docker-compose.yml` (Task 12 creates it; if running out of
  order, add the Metabase service here), `docs/STATUS.md`

**Interfaces:**
- Consumes: Task 10's `mart_determination_outcomes`.
- Produces: table `reporting.mart_determination_outcomes` in the serving
  Postgres database, and a provisioned Metabase dashboard named
  "SNAP determinations".

- [ ] **Step 1: Write the failing materialization test**

```python
@pytest.mark.integration
def test_gold_mart_materializes_into_the_serving_database(built_warehouse, serving_dsn) -> None:
    rows = materialize_gold(duckdb_path=built_warehouse, serving_dsn=serving_dsn)
    assert rows["mart_determination_outcomes"] > 0

    with psycopg.connect(serving_dsn) as conn:
        gold_total = conn.execute(
            "select sum(total_benefit_amount) from reporting.mart_determination_outcomes"
        ).fetchone()[0]
    duck_total = duckdb.connect(built_warehouse).execute(
        "select sum(total_benefit_amount) from main_gold.mart_determination_outcomes"
    ).fetchone()[0]
    assert gold_total == duck_total      # the serving copy is not a re-aggregation
```

- [ ] **Step 2: Implement `materialize.py`**

DuckDB's `postgres` extension does this in-process — no intermediate CSV, no
pandas round-trip:

```python
con.execute("install postgres; load postgres;")
con.execute(f"attach '{serving_dsn}' as serving (type postgres)")
con.execute("create schema if not exists serving.reporting")
con.execute("drop table if exists serving.reporting.mart_determination_outcomes")
con.execute(
    "create table serving.reporting.mart_determination_outcomes as "
    "select * from main_gold.mart_determination_outcomes"
)
```

Gold marts are rebuilt wholesale each run in Phase 1a — incremental
materialization is a Phase 1b concern and would be premature here.

- [ ] **Step 3: Provision Metabase from code**

`provision_metabase.py` is idempotent and drives Metabase's HTTP API:
complete first-run setup if `/api/session/properties` reports
`has-user-setup: false`; create (or find) the Postgres database connection
pointing at the serving database; create (or find) a native question
"Determinations by month and outcome" over
`reporting.mart_determination_outcomes`; create (or find) the dashboard
"SNAP determinations" and add the card. Credentials come from
`CANOPICA_METABASE_USER` / `CANOPICA_METABASE_PASSWORD` env vars with local-dev
defaults in `infra/.env.example`.

`reporting/dashboard/README.md` documents the one command
(`uv run python -m canopica_data.reporting.provision_metabase`) and shows the
resulting page.

- [ ] **Step 4: Write the TMDL semantic model and its test**

`reporting/semantic-model/tables/mart_determination_outcomes.tmdl` declares
the table, its columns with data types and format strings, and three
measures: `Determinations`, `Eligible Rate`, `Average Benefit`. Power BI
Desktop is Windows-only, so this model is authored as text and imported via
the Service (`reporting/powerbi/README.md` documents the import path and
carries exported screenshots) — the model-as-code decision from roadmap §3.3
that also removes the `.pbix`-doesn't-diff risk.

`test_semantic_model.py` parses the TMDL files and asserts every column in
the gold mart's contract appears exactly once and that all three measures are
defined — cheap, but it means the semantic model cannot silently drift from
the mart it describes.

- [ ] **Step 5: Run and commit**

```bash
uv run pytest -m integration && cd .. && make test
git add -A && git commit -m "Task 11: serving-layer materialization, Metabase provisioning, TMDL semantic model"
```

---

## Task 12: Docker Compose — the whole stack, one command

**Files:**
- Create: `infra/docker-compose.yml`, `infra/.env.example`
- Create: `infra/postgres/init/01-databases.sql`
- Create: `portal/Dockerfile`, `portal/web/Dockerfile`, `portal/web/nginx.conf`
- Create: `data-platform/Dockerfile` (the one-shot pipeline runner)
- Create: `data-platform/tests/test_stack_smoke.py` (e2e-marked)
- Modify: `Makefile`, `README.md`, `docs/STATUS.md`

**Interfaces:**
- Produces the service names Task 13's e2e test and the README quickstart
  both use: `postgres`, `portal-api` (8080), `portal-web` (3000),
  `metabase` (3001), and the profile-gated one-shot `pipeline`.

- [ ] **Step 1: Write the init script and Compose file**

`01-databases.sql` creates both databases and the application role with the
least privilege the app actually needs:

```sql
create role canopica_app with login password 'canopica_app';
create database canopica_operational owner canopica_app;
create database canopica_serving owner canopica_app;
```

`docker-compose.yml`: `postgres:16-alpine` with the init script mounted and a
`pg_isready` healthcheck; `portal-api` built from `portal/Dockerfile`
(multi-stage: `maven:3.9-eclipse-temurin-17` build → `eclipse-temurin:17-jre`
runtime), `depends_on: postgres: {condition: service_healthy}`, healthcheck
on `/actuator/health`; `portal-web` built from the Vite app and served by
nginx with `/api` proxied to `portal-api`; `metabase/metabase` on 3001 with
its own internal H2 app database (its content is provisioned by code, so
losing it costs one script run); and `pipeline` under
`profiles: [pipeline]`, running ingestion → dbt build → materialize →
Metabase provisioning as a one-shot container.

- [ ] **Step 2: Write the smoke test**

```python
@pytest.mark.e2e
@pytest.mark.parametrize("url,expected", [
    ("http://localhost:8080/actuator/health", "UP"),
    ("http://localhost:3000/", "Canopica"),
    ("http://localhost:3001/api/health", "ok"),
])
def test_every_service_answers(url: str, expected: str) -> None:
    response = httpx.get(url, timeout=10)
    assert response.status_code == 200
    assert expected in response.text
```

- [ ] **Step 3: Bring it up and run the smoke test**

```bash
make up
docker compose -f infra/docker-compose.yml ps      # every service healthy
cd data-platform && uv run pytest -m e2e tests/test_stack_smoke.py
```

- [ ] **Step 4: Write the README quickstart and commit**

`README.md` gains a quickstart that is exactly what was just run: `make up`,
then `make seed` (generate + load 500 synthetic households), then
`make pipeline` (ingestion → dbt → serving → Metabase), then the three URLs.
A reader with Docker and nothing else must be able to follow it start to
finish.

```bash
git add -A && git commit -m "Task 12: Docker Compose stack, service Dockerfiles, README quickstart"
```

---

## Task 13: End-to-end test + Phase 1a wrap-up

**Files:**
- Create: `data-platform/tests/test_end_to_end.py`
- Create: `docs/demo.md`
- Modify: `.github/workflows/ci.yml`, `README.md`, `docs/STATUS.md`, `CLAUDE.md`

- [ ] **Step 1: Write the end-to-end test**

One test, the whole slice, no mocks:

```python
@pytest.mark.e2e
def test_intake_through_determination_audit_warehouse_and_mart(stack: StackFixture) -> None:
    # 1. Intake — a known household, through the real API.
    household = generate_households(1, seed=1234)[0]
    ids = post_households([household], stack.api_url)[0]

    # 2. Determination — through the real API, as a worker.
    determination = run_determination(stack.api_url, ids.program_request_id,
                                      as_of="2025-06-15", benefit_month="2025-06-01")
    assert determination["policyParameterVersion"] == "SNAP-FY2025"
    assert determination["reasonCode"] in REASON_CODES

    # 3. Trace — persisted, complete, and matching the model that ran.
    trace = get_trace(stack.api_url, determination["determinationId"])
    assert "Excess Shelter Deduction" in trace["decisionResults"]
    assert len(trace["dmnModelHash"]) == 64

    # 4. Audit — the chain covers the new events and still verifies.
    chain = verify_chain(stack.operational_dsn)
    assert chain.ok and chain.rows_checked >= 2

    # 5. Warehouse — bronze, silver, gold all rebuild from the live database.
    extract_to_bronze(stack.operational_dsn, stack.bronze_root, tables=ALL_TABLES)
    assert run_dbt_build(stack.dbt_dir).returncode == 0

    # 6. Mart — the determination is visible, with the right money, under the
    #    parameter version that produced it.
    materialize_gold(stack.duckdb_path, stack.serving_dsn)
    row = query_one(stack.serving_dsn, """
        select determination_count, total_benefit_amount, policy_parameter_version
        from reporting.mart_determination_outcomes
        where benefit_month = date '2025-06-01'
    """)
    assert row["policy_parameter_version"] == "SNAP-FY2025"
    assert row["total_benefit_amount"] == Decimal(determination["benefitAmount"])
```

Step 6's final assertion is the one that matters: the number a report shows
is the same number the rules engine decided, not a re-derivation that happens
to look similar.

- [ ] **Step 2: Add the e2e CI job**

```yaml
  e2e:
    runs-on: ubuntu-latest
    needs: [java, python, dbt]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: docker compose -f infra/docker-compose.yml up -d --build --wait
      - run: cd data-platform && uv sync --dev && uv run pytest -m e2e
      - if: always()
        run: docker compose -f infra/docker-compose.yml logs --no-color > compose-logs.txt
      - if: always()
        uses: actions/upload-artifact@v4
        with: { name: compose-logs, path: compose-logs.txt }
```

- [ ] **Step 3: Run the complete suite, every layer, from clean**

```bash
make down && make up && make seed && make pipeline
make test && make lint && make e2e
cd data-platform && uv run pytest -m integration
```
Record the actual results — including any failure — in `docs/STATUS.md`'s
verification log. A partial pass is reported as a partial pass.

- [ ] **Step 4: Write `docs/demo.md`**

A five-minute walkthrough with the exact clicks and URLs: submit an
application in the portal → open it as a worker → run the determination →
expand the trace panel and read the deduction stack → open the Metabase
dashboard and find that determination in the mart → run the audit chain
verifier and show it green. This is the artifact that makes Phase 1a
*demoable* rather than merely complete.

- [ ] **Step 5: Update `README.md`, `CLAUDE.md`, and `docs/STATUS.md`; commit**

- `README.md`: architecture diagram, the quickstart from Task 12, the
  role-to-subsystem map, and the honest-limitations section pointing at the
  trade-offs doc.
- `CLAUDE.md`: flip Phase 1a from "planned, not started" to "done, verified
  end-to-end", with the same specificity the phase entries in that file
  already use — what was verified, how, and what remains manual.
- `docs/STATUS.md`: all 13 tasks Done, a full verification-log row, current
  position moved to "Phase 1a complete; Phase 1b not started", and the next
  action set to writing the Phase 1b plan.

```bash
git add -A && git commit -m "Task 13: end-to-end slice test, demo walkthrough, Phase 1a wrap-up"
git push
```

---

## Phase 1a definition of done

- [ ] `make test`, `make lint`, `uv run pytest -m integration`, and
      `make e2e` all pass from a clean clone.
- [ ] CI is green on `main`, including the `audit-chain`, `dbt`, and `e2e` jobs.
- [ ] A determination made as of a past date reproduces its original answer
      after both the household's circumstances and the fiscal year have moved on.
- [ ] The audit chain verifies, and a tampered row is detected.
- [ ] `docs/demo.md` runs start to finish against `make up`.
- [ ] Every number in the Metabase page traces back to a determination whose
      DMN trace is inspectable in the portal.
- [ ] `docs/STATUS.md` and `CLAUDE.md` both reflect reality.

## Deferred out of Phase 1a, on purpose

Recorded so a later session does not read an absence as an oversight: Keycloak
and real authentication; caseload-scoped row-level authorization; the mock
external verification interface; MinIO/S3 object storage; Airflow; the full
medallion table set; the asset test, child-support-paid deduction, homeless
shelter deduction, and ABAWD work requirements in the rules engine;
household sizes above 8; broad-based categorical eligibility; incremental
mart materialization; Section 508 conformance work; OpenTelemetry; and
Terraform. Every one of them is Phase 1b or later per the roadmap.
