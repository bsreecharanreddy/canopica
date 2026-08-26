# Canopica — Self-hosted runners for the compose-heavy CI jobs

Status: proposed
Date: 2026-08-25

## 1. Why this exists

This is a private repo on a personal GitHub account, which caps Actions
minutes at 2,000/month. As of today, 1,853 of 2,000 are used, the account
resets 2026-09-01, and the single confirmation run for today's
analytics_copilot fix (`32878703901`) alone cost 63.67 minutes — leaving
roughly 83 minutes for anything else before the reset.

This isn't a one-off squeeze. Three jobs account for the overwhelming
majority of every month's spend, and all three are exactly the jobs Phase
2–4's AI work exercises hardest:

| Job | What it does | Timeout |
|---|---|---|
| `e2e-data-platform` | Brings up `api`, `ui`, `metabase`, `prometheus`, `grafana`, `airflow-webserver`, `airflow-scheduler` via Compose | 25 min |
| `e2e-ai` | Brings up `opensearch`, `ollama`, `api`; runs the full AI-layer e2e suite against a live local model | 30 min |
| `ai-eval` | Brings up `opensearch`, `ollama`; runs the RAGAS/DeepEval eval-suite gate against a live local model | 35 min |

The `canopica-recurring-ci-failure` skill already measured this once:
703 of 2,000 minutes burned in a single 24-hour debugging session,
60% of it from `e2e-ai` and `ai-eval` alone. Today's session repeated the
pattern. Every future phase (3: Case Intake AI, 4: Compliance & Integrity
AI) adds more of exactly this kind of iteration, so the constraint recurs
monthly, not just this week.

GitHub-hosted minutes are the free tier's actual bottleneck. A
self-hosted runner is billed **$0** in Actions minutes no matter where it
physically runs — GitHub only meters its own hosted compute. That fact is
what makes every option below work at all; the only real question is
*where* the self-hosted runner lives.

## 2. Where "where" actually matters

**This dev machine is not a free place to put it.** `infra/docker-compose.yml`
already runs persistently here for local development (`make up`), bound to
fixed host ports (5432 postgres, 9200 opensearch, 11434 ollama, 8080
api, and others). All three heavy CI jobs bring up an overlapping
subset of that *same file* on those *same* ports — a runner registered on
this laptop collides with local dev the moment both try to bind a port,
which given this is the one machine development actually happens on, is
the common case, not an edge case. It would also tie CI's availability to
this laptop being on, awake, and not asleep mid-workday.

**A cloud VM sidesteps that, but not for free.** The stack's real memory
footprint is already measured in this repo's own `docker-compose.yml`
comments, not guessed: OpenSearch is pinned to a 2GB JVM heap (raised
twice after real `Memory Circuit Breaker is open` failures at smaller
sizes), and Ollama holds both models resident at once — llama3.2:3b
(~2.7GB) plus nomic-embed-text (~376MB) — before api's own JVM or
the OS. This repo has already hit real OOM/circuit-breaker incidents
running this exact stack on a 7.65GB Docker VM. Azure's actual free-tier
VM (B1S: 1 vCPU, 1GB RAM, 12 months on a new account) is roughly an order
of magnitude too small; it would fail differently, not run for free.

**Found while checking this against the repo, not assumed**:
`infra/azure/README.md` states plainly that its Terraform is "reference
only... nothing here is ever applied against a live subscription" — a
deliberate choice so anyone cloning this repo can run it with zero cloud
credentials and zero cloud cost. A runner VM is a *real, applied*
resource, which is a different category from that reference config and
must not be folded into it — doing so would quietly break the exact
property that config was written to guarantee.

## 3. Options

### Option A — self-hosted runner on this laptop, with a port-remapped Compose override

Only the 3 heavy jobs move to `runs-on: [self-hosted, canopica-heavy]`,
using a new `infra/docker-compose.ci-ports.yml` override (remapped host
ports, e.g. `5432→15432`) plus an explicit `-p canopica-ci` project name,
so CI's stack and a running `make up` stack coexist as independent Compose
projects on the same host.

- **For:** solves the port collision, zero cloud spend.
- **Against:** CI now depends on this laptop being on and awake; Compose
  jobs compete with local dev for host CPU/RAM/Docker daemon capacity even
  once ports no longer collide; no interview-relevant skill beyond what
  this project already demonstrates.

### Option B — self-hosted runner on an ephemeral, correctly-sized Azure VM (recommended)

One VM, sized to what the stack actually needs (`Standard_B2ms`: 2 vCPU,
8GB RAM, roughly matching the 7.65GB this project's own Docker VM already
runs on), provisioned **once** by a small, separate Terraform root —
**not** `infra/azure/`, a new `infra/azure/ci-runner/`, applied for real
by the user from their own machine with their own subscription, exactly
because §2 found that `infra/azure/` is deliberately never-applied and
mixing an actually-provisioned resource into it would break that
guarantee for every future reader of that directory.

That one-time apply does the setup a real deployment would automate:
resource group, the VM, an NSG with **no inbound rules at all** — GitHub's
own self-hosted runner agent works by polling GitHub outbound over HTTPS,
so nothing needs to reach the VM from the internet, which also means it
needs no public IP — and a cloud-init/custom-script extension that
installs Docker and the GitHub Actions runner agent and registers it once
against this repo. The VM is left **deallocated** (stopped — Azure does
not bill compute for a deallocated VM, only its small OS disk, on the
order of $1-2/month) after that initial registration succeeds.

Per-run orchestration then lives in `ci.yml` itself, not in Terraform: a
cheap `ubuntu-latest` job authenticates to Azure via an OIDC federated
credential (`azure/login`, no static secret stored in GitHub) and runs
`az vm start` before the 3 heavy jobs, which then run on
`[self-hosted, canopica-heavy]` as GitHub holds them until the runner
comes online; a final `if: always()` cleanup job runs `az vm deallocate`
regardless of whether the heavy jobs passed. Terraform never runs inside
CI for this — it provisioned the box once, and `az vm start`/`deallocate`
are what every subsequent run actually uses.

Billed only for actual runtime, but "actual runtime" depends entirely on
push cadence, and this project's own real cadence is not sparse: 15-20
pushes/day during an active debugging session, per today's session. One
real data point — today's confirmation run cost 63.67 total job-minutes
for one push where all 3 heavy jobs fired — means that if even half of a
15-20-push day touches `ai/` or other non-docs code, that's 450-640
minutes/day of real heavy-job runtime, not 60-90. At that volume, B-series
burstable pricing lands at roughly **$20-50/month** on a plain
start/stop-per-push pattern — still far cheaper than GitHub's per-minute
overage pricing at the same volume (well over $100/month), but not the
"a few dollars" this section originally estimated on a lighter usage
assumption.

That points at a real dependency this option only works well alongside:
Option C's local-repro-before-push discipline (`canopica-recurring-ci-
failure`'s step 6) is what actually keeps the push count — and therefore
this VM's real monthly cost — low. Per-job start/stop is deliberately kept
simple (no idle-shutdown scheduler) on the assumption that most iteration
happens locally and only verified changes get pushed; building smarter
VM-lifecycle machinery would be solving the wrong problem if the push
count itself is the thing driving cost up.

- **For:** removes the laptop dependency and resource contention Option A
  keeps; near-zero cost via start/stop instead of always-on; extends the
  Azure/Terraform work this project already has (`infra/azure/`) with a
  second, honestly-labeled real one, which is a legitimate interview
  story (ephemeral, cost-aware infrastructure, not just "a VM").
- **Against:** most moving parts of any option here — Terraform, an NSG,
  OIDC federation, and two orchestration jobs in `ci.yml` versus Option
  A's one config file. A `main` push while the start step is failing
  queues rather than fails, same operational caveat Option A has.

Azure Container Instances was considered as a lighter-weight alternative
to a VM and rejected: it doesn't reliably support the nested Docker/Docker
Compose these jobs actually run, which a VM with a real Docker daemon
does without qualification.

### Option C — no new infrastructure; attack the demand side only

Tighten what `canopica-recurring-ci-failure`'s step 6 already prescribes
but today's session didn't fully follow — reproduce `ai/`-layer changes
locally against `make up` before pushing, rather than using a push as the
first real test. Combine with the `changes` job's existing
`ai_eval`/`code` path filters and, if needed, a one-time purchase of extra
Actions minutes as a bridge to a reset date.

- **For:** zero new infrastructure, zero new failure modes, works
  immediately.
- **Against:** doesn't fix the structural recurrence — Phase 3/4 hits the
  same wall for the same reason. Right standing practice regardless of
  what else is adopted, not sufficient alone.

## 4. Recommendation

**Option B**, with Option C's demand-side practices kept as standing
discipline regardless — they cost nothing and reduce how often the runner
needs to spin up at all.

The deciding argument: B is the only option that removes both the
structural constraint (GitHub-hosted minutes are fixed) *and* the
laptop-availability/contention problem A keeps, without paying for an
always-on box. Its extra complexity buys something real — the ephemeral
start/stop pattern is close to how production self-hosted runner fleets
actually behave (scale-to-zero), which is a better demonstration than a
static VM would have been, and a better one than Option A's laptop
approach.

## 5. Consequences if adopted

- **New, separate Terraform root**: `infra/azure/ci-runner/` —
  deliberately not part of `infra/azure/`, whose README states it is
  reference-only and never applied; this one is real and applied once, by
  hand, from the user's own machine with their own subscription
  credentials. Needs its own state (a remote backend, e.g. Azure Storage,
  is the right answer even for a single operator — local state tied to
  this laptop would make the one-time apply as fragile as Option A's
  laptop dependency was supposed to avoid).
- **`ci.yml` changes**: the 3 heavy jobs' `runs-on` becomes
  `[self-hosted, canopica-heavy]`; a new `start-runner` job (OIDC login,
  `az vm start`) gates them; a new `stop-runner` job (`if: always()`,
  `az vm deallocate`) follows them. The 8 fast jobs are untouched and stay
  on `ubuntu-latest`.
- **Security — must be reversed or restricted before the repo goes
  public.** Self-hosted runners on a repo that accepts fork PRs are a
  known arbitrary-code-execution vector (a fork PR's workflow executes on
  the runner's own hardware). Current exposure is low — STATUS.md already
  records this repo as private with only this user pushing — but
  `canopica-heavy` must be decommissioned or restricted to non-fork
  workflow runs before the visibility decision changes. No inbound
  network exposure exists independent of that (no public IP, no open
  ports), which narrows the residual risk to exactly that one vector.
- **Operational**: `ci.yml`'s concurrency block never cancels an in-flight
  run on `main` by design (every commit needs its own verified result). A
  `main` push where `start-runner` fails or the VM is slow to come online
  queues rather than fails — accepted, same as Option A would have had,
  not worth building automatic failover to `ubuntu-latest` for.
- **Not a phase task.** This is CI/infrastructure tooling, not part of
  any `docs/plans/` phase plan. Implementation still follows the standing
  discipline: `terraform validate`/`fmt` on the new root, `docs/STATUS.md`
  gets this decision's row, and it lands as its own scoped commit(s), not
  bundled with unrelated work.
- **Tradeoffs-doc update**: the `CI/CD` row's fidelity mark moves from
  **≈** to **~** for the compose-heavy jobs specifically, with the
  what-would-change column naming the real production equivalent
  (an autoscaling self-hosted runner pool — e.g. GitHub's own Actions
  Runner Controller on Kubernetes — rather than one VM manually started
  and stopped).

## 6. Addendum (2026-08-25): widened to every job, not just the 3 heavy ones

The scope above was deliberately narrow — only `e2e-data-platform`,
`e2e-ai`, and `ai-eval` moved to `canopica-heavy`; the 8 fast jobs stayed
on `ubuntu-latest` since they were already cheap. That assumption broke
for real the same day this doc's Option B was first applied: this
private repo's GitHub Actions minutes were fully exhausted (2000/month
cap), and every `ubuntu-latest` job — including the cheap ones, including
`changes` itself — started failing outright with "recent account
payments have failed or your spending limit needs to be increased" (run
`32913936148`), not degrading gracefully or queuing. A private repo past
its included minutes needs either a raised spending limit/working payment
method, or to stop depending on GitHub-hosted minutes at all; this repo's
own push cadence (15-20/day during active work, per `docs/STATUS.md`)
makes the second the more durable fix.

**Every job now runs on `canopica-heavy` except `changes`, `start-runner`,
and `stop-runner`.** That trio is structurally irreducible, not an
oversight: deciding whether to start the VM, and then actually starting
it, cannot itself run on the VM being started. Those 3 jobs are cheap
(seconds each) and still need *some* GitHub-hosted minutes/working
billing to run at all — this change reduces GitHub Actions usage by
roughly 90%+ per run, it does not eliminate it, and does not by itself
unblock a fully-exhausted account. `start-runner` also dropped its
`needs: [changes]`/`if: needs.changes.outputs.code == 'true'` gate:
it used to start the VM only when the 3 heavy jobs' own `code` flag
was true, but now every job (including the 8 previously-`ubuntu-latest`
ones, which already ran unconditionally on every push, docs-only
included) needs the VM, so starting it is unconditional too, and no
longer waits on `changes` to finish first.

**Real consequence, not free**: a single self-hosted runner processes one
job at a time. Jobs that used to run in GitHub-hosted parallel (up to 11
of them) now serialize on this one VM — a real-code push's total CI
wall-clock time goes up accordingly. Accepted as the right trade for this
project's situation (near-zero GitHub-hosted minutes beats a fast CI run
that can't start at all), not revisited here as a new decision.
