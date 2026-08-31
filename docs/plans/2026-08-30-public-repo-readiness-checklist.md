# Public Repo Readiness — Final-Pass Checklist

Not a phase in the AI-capability roadmap — this is the wrap-up checklist
for everything already deferred, across many separate decisions, to "once
active development is complete, right before the repo goes public"
(`docs/STATUS.md`'s "Repo visibility" decision row, confirmed
2026-08-23). Consolidated here for the first time so nothing gets missed
when this actually starts — every item below already has its own real
decision recorded elsewhere; nothing here is new scope.

**Sequencing:** Phase 5 (`docs/plans/2026-08-30-phase-5-implementation-
plan.md`) is the last real engineering work. This checklist runs after
Phase 5's live demo is done and screenshotted — it's operational/
documentation wrap-up, not new capability.

---

## 0. Time-sensitive — check now, don't wait for the rest of this list

- [x] **Azure free-trial status, re-checked 2026-08-31** (superseding the
      2026-08-30 note below, which was written before Phase 5 Task 2's
      apply — that apply has since completed and been torn down cleanly,
      so the original "do this before Task 2 starts" urgency no longer
      applies). Confirmed live via `az account subscription show`:
      `quotaId: FreeTrial_2014-09-01`, `spendingLimit: On` — Azure's hard
      spend-cap is still active, no runaway-bill risk. Trial start date
      found directly this time (`az billing account list`'s
      `systemData.createdAt`: `2026-08-25T21:35:32Z`), so the 30-day
      window converts to pay-as-you-go around **2026-09-24** — not urgent
      today. **Decision (2026-08-31): switching CI to GitHub-hosted
      runners**, since the repo will be public by then and public repos
      get free/unlimited GitHub-hosted Actions minutes — see the new
      note in §5 below. The NAT Gateway/VM stay running until that flip
      (they're live CI infra, not idle spend) rather than being torn down
      separately first.

  Original 2026-08-30 note, superseded, kept for the record: checked live
  that day, the subscription read the same `quotaId`/`spendingLimit` as
  above, and the CI runner VM was alive and actively running jobs. What
  CLI couldn't get then was the precise days-remaining on the 30-day/$200
  credit window — the consumption/credit-balance APIs returned nothing
  usable for this account type (resolved above via the billing account's
  `createdAt`). The teardown command recorded then, scoped to just the NAT
  Gateway (`terraform destroy -target=azurerm_subnet_nat_gateway_association.this
  -target=azurerm_nat_gateway_public_ip_association.this
  -target=azurerm_nat_gateway.this -target=azurerm_public_ip.nat` in
  `infra/azure/ci-runner/`), is superseded by a full untargeted destroy of
  that whole directory's state, bundled into §5's flip step, since the VM
  itself is going away too, not just its NAT Gateway.

## 1. Content/documentation pass

- [x] **"Customer/worker portal" language pass — checked 2026-08-31,
      resolves to no changes needed.** `2026-08-20-phase1-vertical-slice.md`
      is explicitly frozen by CLAUDE.md's own "Read this first" section
      ("kept as-is... as a record of how the design evolved") — a style
      pass isn't the right move there regardless of what this bullet
      guessed at when written. Grepped
      `2026-08-21-tech-stack-and-production-tradeoffs.md` directly: every
      hit ("citizen portal"/"worker portal" in the Web UI row's *real
      production equivalent* column, "customer-communications-management
      product," "customer-managed keys") describes a real system's
      generic industry pattern or vendor terminology, never Canopica's
      own self-description — the opposite of the pitch-copy framing
      concern the 2026-08-25 decision was actually about. `docs/plans/`
      and `docs/STATUS.md` hits are all inside dated, already-executed
      historical records (verification-log rows, a completed phase's own
      plan doc) — rewriting those for phrasing would misrepresent what
      was actually written at the time.
- [x] **Add a short callout — done 2026-08-31.** README's "Honest
      limitations" section gained a bullet stating, past tense, that CI
      ran on a self-hosted Azure VM for six days (2026-08-25 – 2026-08-31)
      after the private-repo GitHub Actions minutes cap was exhausted for
      real (run `32913936148`), and moved back to GitHub-hosted runners at
      this flip.
- [x] **Swap the public demo's inference model — done 2026-08-31.**
      `deepseek/deepseek-chat` → `anthropic/claude-haiku-4.5` in
      `ai/src/canopica_ai/config.py`, price pair re-verified live against
      OpenRouter's own API at swap time ($1.00/$5.00 per MTok, unchanged).
      See `docs/STATUS.md`'s verification log for the full record.

## 2. Public demo — the actual live deploy

- [ ] **`fly deploy` for real** (Task 9 Step 5's remaining piece) — the
      Dockerfile/`fly.toml` are already written and locally verified;
      only the live deploy (~$22/mo starts billing) and Step 7's live
      smoke check are still deliberately held back.
- [ ] Confirm the deployed demo actually answers a real question end to
      end once live (the smoke check itself).

## 3. GitHub account/profile

- [ ] **Profile README** (`<username>/<username>` special repo) — add
      Canopica project details.
- [ ] **Bio field** — reflect the project.
- [ ] **Pinned repositories** — feature Canopica.
      (All three explicitly deferred 2026-08-30 — "hold off for now, keep
      it as an item to do once we flip to public.")

## 4. Interview material

- [x] **Final regeneration of the interview-story-bank Artifact — done
      2026-08-31.** Rebuilt from the Gist's full 30-story content (up from
      28 as of 2026-08-30 — two more landed the same day). Published as a
      new artifact rather than updated in place, since the user had
      switched claude.ai accounts and an `url`-targeted update to the old
      artifact was blocked by the auto-mode permission classifier:
      <https://claude.ai/code/artifact/f956d495-1a7e-492c-981b-4de1cd34a1ce>
      — see `reference_canopica_interview_story_bank` memory for the full
      design/build record. Link sent to the user; not yet confirmed
      working in their browser.
- [ ] **Delete the Gist** once the Artifact is regenerated from it — it
      was always the interim working copy, not the destination. **Holding
      until the user confirms the new Artifact link actually opens for
      them** — this project has a documented history of a publish
      succeeding on the tool side but not being visible to the user due
      to an account mismatch (2026-08-23), so "published successfully"
      alone isn't enough to treat the Gist as safe to delete yet.

## 5. Loose ends needing an explicit decision (not silently dropped)

- [x] **`CLAUDE.md`, `.claude/agents/`, `.claude/skills/canopica-code-
      review/`** — resolved 2026-08-31: both were real, already-in-use
      tooling (not gitignored, sitting alongside four already-tracked
      sibling skills in the same directory), so committed for real
      (`a7d782c`) rather than discarded.
- [x] **Cyclomatic-complexity static analysis** — resolved 2026-08-31,
      folded in: ruff's `C901`/mccabe added to `ai/`, `data-platform/`,
      `worker/` `pyproject.toml` (`max-complexity = 10`, i.e. 11+ fails,
      matching the manual audit's own "above 10, not at 10" rule); one
      real hotspot found and fixed, `OpenRouterJudgeModel.generate`
      (ruff's actual count: 11 — the manual audit's 2026-08-27 hand-count
      of 10 for this same function undercounted by one, the same class of
      miss that audit's own entry flagged happening elsewhere that same
      day), fixed by extracting `_extract_content` for the 200-response
      interpretation logic. `maven-pmd-plugin` 3.28.0 added to the root
      `pom.xml`, bound to `verify` (no CI/Makefile change needed — both
      `make lint` and `make test` already run the commands that pick
      these up); `pmd-ruleset.xml` scoped to just `CyclomaticComplexity`,
      deliberately not PMD's full "design" category. One boundary
      mismatch found and fixed live: PMD reports at complexity `>=`
      threshold while ruff reports at `>` — PMD's default `10` flagged a
      real method (`PolicyParameterPublishService.validate`) at exactly
      10 that ruff's semantics wouldn't have; set `methodReportLevel=11`
      so both tools agree on the same "above 10" rule rather than forcing
      an artificial split of three clean, independent guard clauses. Full
      `make lint`/`make test` verified clean after.
- [x] **CI-runner flip + Azure teardown — done 2026-08-31.**
      `CI_LIGHT_RUNNER`/`CI_HEAVY_RUNNER` cleared, confirmed green on
      GitHub-hosted `ubuntu-24.04` runners (run `33415354007`, all 14
      jobs), then untargeted `terraform destroy` in
      `infra/azure/ci-runner/` — 17 resources destroyed, verified gone
      (`az group exists` → `false`, empty `terraform state list`, no
      leftover Entra ID app). See `docs/STATUS.md`'s verification log.
- [x] **Repo visibility itself — done 2026-08-31.** Flipped to public
      (`gh repo edit --visibility public`), branch ruleset `main-protection`
      created (blocks deletion/force-push, requires the 9 always-run CI
      jobs — deliberately excludes the 3 path-gated ones — no PR
      requirement per explicit user choice, so direct pushes to main keep
      working). CI badge and repo page both confirmed `200` to an
      unauthenticated request. See `docs/STATUS.md`'s verification log.

---

## Definition of done

- [ ] Every checkbox above resolved — either done, or (for the two
      "loose ends" items) explicitly decided and recorded, not silently
      skipped.
- [ ] `docs/STATUS.md` updated in the same commit as the flip itself,
      same discipline as every other change to this file.
- [x] Repo is public, CI badge renders for a signed-out viewer, branch
      protection is on. Confirmed 2026-08-31 (both `200` to an
      unauthenticated request; ruleset `main-protection` active).
