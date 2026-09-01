# Canopica UI

React 19 + TypeScript + Vite client for Canopica — see the [repo root
README](../README.md) for what the whole system is. This package is the
`A["React UI"]` box in that README's architecture diagram: a role-based
client against the Case & Determination API, styled with the "Public
Ledger" design system (`docs/design/2026-08-27-ui-modernization-public-ledger.md`
in the repo root) — civic-editorial in tone, on purpose, since the subject
matter is a real benefits determination, not a generic SaaS dashboard.

## Stack

- React 19, TypeScript, Vite 8
- Tailwind CSS 4 + `radix-ui` primitives, `class-variance-authority` for variants
- `react-router-dom` for routing, `react-oidc-context`/`oidc-client-ts` for Keycloak OIDC login
- `react-i18next` for localization (Phase 3 correspondence translation surfaces this in the UI too)
- Vitest + React Testing Library + `vitest-axe` for component and accessibility tests
- `oxlint` for linting (not ESLint — see `oxlint.json` at the repo root)

## Running locally

From the repo root, `make up` brings up the full stack (Postgres, API,
UI, Metabase) via Docker Compose — that's the normal way to run this.
To run just the UI against an already-running API:

```bash
npm install
npm run dev      # http://localhost:3000, proxies /api -> localhost:8080
```

Other scripts:

```bash
npm test              # vitest run — component + accessibility tests
npm run test:coverage # vitest run --coverage
npm run typecheck      # tsc -b --noEmit
npm run lint            # oxlint
npm run build           # tsc -b && vite build
```

## Key pages

`src/pages/` — one file per real, wired screen (no mockups):

| Page | Role | What it does |
|---|---|---|
| `IntakePage` | citizen | Submit a program-eligibility application |
| `WorkerCasesPage` | worker | Caseload queue, claim/assignment |
| `CaseDetailPage` | worker | Run a determination, view the DMN trace and audit trail |
| `PolicyQaPage` | either | RAG policy Q&A with grounded citations |
| `RuleAuthoringPage` | worker | Human-gated policy-parameter publishing copilot |
| `DocumentReviewPage` | worker | Review AI-classified/extracted uploaded documents |
| `NoticeReviewPage` | worker | Review and approve AI-drafted correspondence before dispatch |
| `FraudReviewPage` | supervisor | Fraud-risk triage review queue |
| `QcReviewPage` | supervisor | QC / payment-error-rate sampling review |
| `SlaMonitorPage` | worker/supervisor | At-risk case aging and stall-reason monitor |
| `SopCopilotPage` | worker | Caseworker SOP copilot |

Every AI-assisted page above surfaces the model's output as something a
human reviews and acts on, never as an auto-applied decision — the same
"AI assists, never decides" boundary the root README states as this
project's one governing principle.
