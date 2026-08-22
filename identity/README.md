# Identity — Keycloak realm configuration

Two realms, declarative, imported on container start (`--import-realm`) —
reviewable in a diff, same "model-as-code" preference this repo already
applies to the TMDL semantic model and the dbt project.

- **`ies-workers`** — caseworker/supervisor accounts. Directly-provisioned
  test users (`worker.sam` / `IesWorker123!`, `supervisor.robin` /
  `IesSupervisor123!`), not real SSO/IdP brokering — brokering to a real
  enterprise IdP is what "SSO simulation" (roadmap §3.3) stands in for
  conceptually. Realm roles `WORKER` / `SUPERVISOR` / `ADMIN` map directly
  onto `worker.role`'s existing `CHECK` constraint values.
- **`ies-citizens`** — self-registration enabled (`registrationAllowed`),
  matching how a real applicant creates their own account. No realm roles:
  authenticating against this realm at all is what the portal API treats
  as `CUSTOMER` — there's only one kind of citizen account.

Both realms also carry a confidential `test-worker` / `test-customer`
client with Direct Access Grants enabled — used only by
`data-platform/tests/test_end_to_end.py` and the Maven test suite to fetch
real tokens for a seeded test user, the same "hit the real thing" standard
Phase 1a's own e2e test already holds everything else to. Never used by a
real user; the "secret" values (`test-worker-secret`,
`test-customer-secret`) are local-dev-only, same treatment as this repo's
existing Metabase admin password in `infra/docker-compose.yml` — not real
secrets, not a security boundary.

## Dev-mode Keycloak, stated plainly

`infra/docker-compose.yml` runs Keycloak with `start-dev`, no TLS, a
bootstrap admin whose credentials are also local-only. This is the same
"$0, self-hosted, local-first" tradeoff this whole repo already makes
everywhere else (`docs/design/2026-08-21-tech-stack-and-production-tradeoffs.md`
§5) — a real deployment runs Keycloak clustered, behind TLS, with a real
admin credential in a real secrets manager, none of which changes any
application code, only deployment configuration.

## Regenerating the export

These files are hand-written, not `kc.sh export`'d from a running
instance — Keycloak's own export includes a lot of per-install noise
(internal ids, default client scopes, etc.) that would make this file
unreviewable as a diff. If future changes are made by hand in the
Keycloak admin console during development, re-derive the equivalent JSON
change by hand too rather than pasting a full raw export over this file.
