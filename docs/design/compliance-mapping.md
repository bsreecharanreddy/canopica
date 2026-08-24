# Compliance mapping — NIST 800-53 & IRS Pub 1075

Phase 1b Task 7. Same standard the hash-chained audit log already sets for
itself: a control is listed here only if there's real, running code behind
it, named explicitly, not a claim of "we consider this." Where a control
is deliberately not fully met, that's stated too — see "Known gaps" at the
end, and `docs/plans/2026-08-22-phase-1b-implementation-plan.md`'s own
"Deferred out of Phase 1b, on purpose" list for the fuller reasoning behind
each.

This maps *this repo's* controls, for a *synthetic-data portfolio project*
— it documents what a real state SNAP/TANF system's control set would need
to demonstrate, and how this codebase's substitutions stand in for the
real thing. It is not a real ATO (Authorization to Operate) package, and
never claims to be one; see
`docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md` for the
fidelity/cost tradeoff behind every substitution named below.

## NIST 800-53 Rev. 5

### AC-3 — Access Enforcement

Every worker-facing API endpoint requires a valid Keycloak-issued JWT
(`portal/src/main/java/canopica/portal/config/SecurityConfig.java`,
`oauth2ResourceServer(...)`), replacing Phase 1a's `X-Canopica-Role` header
entirely (Task 1). `KeycloakWorkerSyncFilter` provisions the corresponding
`worker` row from the token's claims on first use — every subsequent
`Authentication#getName()` call resolves to a real Keycloak `sub`, not a
role string.

### AC-6 — Least Privilege

Row-level authorization via `case_assignment` (Task 2):
`CaseAssignmentService` — an unassigned `WORKER` gets 403 on a household
they have no active assignment for; a `SUPERVISOR` can view any household,
but that override is itself logged distinctly (see AU-2 below), not
silently allowed. `SupervisorController` gates reassignment and
sensitivity-flagging to the `SUPERVISOR` role only.

The `pii_token` vault (Task 7, `V11__pii_token_vault.sql`) is
`revoke all ... from public`, narrower than the general operational-schema
access every other table gets — see "Known gaps" for why this repo's
single-application-role setup can't yet demonstrate a second, narrower
role holding the grant.

### AU-2 / AU-3 — Event Logging, Content of Audit Records

The hash-chained `audit_event` table (`V6__audit_event.sql`, Task 6 of
Phase 1a) records `APPLICATION_SUBMITTED`, `DETERMINATION_MADE`,
`CASE_VIEWED`, `VERIFICATION_UPDATED`, and — added by Phase 2 Task 3
(`V16`) — `POLICY_PARAMETER_PUBLISHED` events with actor, subject,
timestamp, and a structured payload. That last one is a configuration-
change record rather than a case-access one: it names the human who put a
set of benefit figures into force, which the `policy_parameter_proposal`
row also records but cannot attest to, being mutable by design.
Task 2 extended `CASE_VIEWED`'s
payload with `in_assignment: boolean`, so a supervisor override is a
distinctly identifiable event, not indistinguishable from routine
in-caseload access — the exact shape `mart_access_review` (Task 5) reports
against.

### AU-9 — Protection of Audit Information

`audit_event_chain()` (`V6__audit_event.sql`) computes `prev_hash`/`hash`
in a database trigger under a transaction-scoped advisory lock — the
application supplies only the payload, and cannot choose, skip, or
backdate a hash. `canopica_data.audit.verify_chain` independently re-derives
the chain and reports the first row where it diverges from what's stored;
`test_verify_chain.py::test_detects_a_tampered_payload` proves this
against a real superuser-level row edit (the one actor no
application-level control could stop), not a mocked tamper.

### AU-10 — Non-repudiation

Same mechanism as AU-9: a hash chain rooted in `actor_id` (the JWT `sub`,
per AC-3 above) makes a later denial of "I didn't view/decide this"
unsupportable without also breaking the chain in a way `verify_chain()`
detects.

### SC-28 — Protection of Information at Rest

`pii_token` (Task 7): `first_name`/`last_name` no longer reach the
warehouse in the clear or as a one-way hash — `dim_person.name_token`
stores an opaque token; the real value is `pgcrypto`-encrypted
(`pgp_sym_encrypt`) in the vault and recoverable only through
`canopica_data.governance.tokenize.detokenize`, a separate, explicit call, not
a normal column read.

### SC-12 / SC-13 — Cryptographic Key Establishment & Management; Use of Cryptography

`pgcrypto`'s `pgp_sym_encrypt`/`pgp_sym_decrypt` (symmetric, OpenPGP-mode)
back the vault. The symmetric key is `Settings.pii_encryption_key`
(`data-platform/src/canopica_data/config.py`) — a local-dev default,
override-by-environment-variable, same pattern already used for
`metabase_password`. See "Known gaps": this is not HSM-backed key
management, and is explicitly marked as a substitution, not an equivalent.

## IRS Pub 1075 — Federal Tax Information (FTI) safeguards

Applied to the mock external verification interface (Task 3), which
stands in conceptually for the kind of federal-data-matching interface
(e.g., IRS income verification) Pub 1075 governs, even though nothing here
touches real FTI:

- **Need-to-know access**: `VerificationController`'s endpoints require
  the caller to hold the active `CASE_ASSIGNMENT` on the household (reuses
  Task 2's authorization check) — the same person/household boundary as
  every other case-scoped read.
- **No raw response beyond need-to-know**: `GET
/api/program-requests/{id}/verifications` returns `verification.status`
  and, once resolved, `verification_response.outcome` — never
  `verification_response.raw_payload`. `VerificationController`'s response
  DTO (`VerificationStatusResponse`) has no field for it at all, not just
  an unpopulated one.
- **Every access logged**: both the request and the received-response are
  their own `VERIFICATION_UPDATED` audit-chain events
  (`stage: REQUESTED`/`stage: RECEIVED`), covered by the same AU-2/AU-9/
  AU-10 mechanisms above.
- **Encryption in transit**: out of scope for this local demo (no TLS
  termination is modeled anywhere in `infra/docker-compose.yml`) — a real
  deployment's TLS posture is the tech-stack tradeoffs doc's Platform tier
  concern, not something this mock interface itself models.

## Known gaps

Stated plainly rather than implied by omission:

- **Single application role.** `canopica_app` is both the portal's and the
  data-platform pipeline's Postgres role. AC-6's "narrower grant" language
  above (`revoke all on pii_token from public`) is real and enforced
  against every *other* role, but there is currently no second, narrower
  role for a real deployment's "who may call `detokenize()`" boundary to
  be demonstrated against. A real deployment would add a dedicated,
  narrowly-granted role for that call path specifically.
- **Vault shares a failure domain with the data it protects.** `pii_token`
  lives in the same Postgres instance as `person`/`household` — compromising
  the operational database compromises the vault too. A real tokenization
  product runs out-of-band with its own credential, often HSM-backed keys.
  Recorded as a **substituted (~)** fidelity mark in the tech-stack
  tradeoffs doc's Data tier, §4.15.
- **No periodic access recertification.** `CASE_VIEWED`'s `in_assignment`
  flag makes an out-of-caseload view visible in `mart_access_review`, but
  nothing here periodically re-certifies that existing `case_assignment`
  rows are still appropriate — a real deployment's access-review process
  would run on a schedule, not just flag anomalies as they occur.
- **True case-sealing isn't built.** `household.is_sensitive` (Task 2)
  raises the audit signal on a flagged case but doesn't block access —
  every role that could already see the case still can. Real sealing (an
  override workflow required before access) is out of Phase 1b's scope by
  design; see the implementation plan's "Deferred out of Phase 1b."
- **No TLS anywhere in the local Compose stack** — plaintext HTTP/Postgres
  wire protocol between containers on the Compose network. Real-deployment
  equivalent is the tech-stack tradeoffs doc's Platform tier.
