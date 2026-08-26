# Self-hosted CI runner (real, applied)

Unlike `../` (reference only, `terraform validate`/`fmt` in CI, never
applied), this configuration is meant to be run for real, from the
operator's own machine with their own subscription. See
`docs/design/2026-08-25-self-hosted-ci-runners.md` for the full
reasoning — this README covers only how to actually use it.

## What this provisions

One `Standard_D2s_v7` (2 vCPU, 8GB) Ubuntu 24.04 VM — `variables.tf`'s
`vm_size` default. Neither the originally-planned B2ms nor D2s_v5 ever
worked on this subscription: both came back `NotAvailableForSubscription`
in eastus *and* centralus (confirmed via a full `az vm list-skus
--location centralus --all` dump, not a per-SKU guess) — a
subscription-level VM-family restriction on new/free-trial Azure
subscriptions, not the per-region capacity issue it first looked like.
D2s_v7 is the first size in that search with `restrictions: []` and free
quota (`Standard Dsv7 Family`, 4/4 vCPUs) on this subscription, same
2 vCPU/8GB shape as the other two, sized to what
`infra/docker-compose.yml`'s `opensearch` + `ollama` + `api` actually
need (measured in that file's own comments, not guessed) — no public IP,
no inbound network rules at all, GitHub's runner agent reaches out over
outbound HTTPS. Plus an Azure AD app registration with two GitHub OIDC
federated credentials (`push` to `main`, and `pull_request`), scoped to
**Virtual Machine Contributor** on just this resource group — enough for
`ci.yml`'s start/stop jobs to start and deallocate the VM, nothing more.

## One-time setup

1. `az login` (interactive — this step can't be scripted).
2. From this directory:
   ```
   terraform init
   terraform plan    # read this before applying anything real
   terraform apply
   ```
3. Wait a few minutes for cloud-init to finish (installs Docker + the
   runner binary; does not register the runner — see why in
   `cloud-init.yaml`'s own comment). No output tells you when it's done;
   `az vm run-command invoke --resource-group <rg> --name <vm> --command-id
   RunShellScript --scripts "cloud-init status --wait"` will block until
   it reports `done`.
4. Get a fresh runner registration token (expires in ~1 hour):
   ```
   gh api -X POST repos/bsreecharanreddy/canopica/actions/runners/registration-token -q .token
   ```
5. Run `terraform output one_time_registration_command`, substitute the
   token from step 4 for `<REGISTRATION_TOKEN>`, and run it. This
   registers the runner (label `canopica-heavy`) and installs it as a
   systemd service — it starts automatically on every future boot, so
   this step never needs repeating even though the VM itself gets
   stopped and started constantly.
6. Confirm it shows up under the repo's Settings → Actions → Runners.
7. Set three repo variables (Settings → Secrets and variables → Actions →
   Variables) from `terraform output`: `AZURE_CLIENT_ID`,
   `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. None of these are secrets
   — OIDC federation means no client secret exists to leak.
8. `az vm deallocate --resource-group <rg> --name <vm>`. Azure does not
   bill compute for a deallocated VM, only its ~32GB OS disk (a couple
   dollars a month at rest). Everything from here on is `ci.yml`'s own
   `az vm start`/`az vm deallocate` steps, once per run.

## Ongoing operation

Nothing to do. `ci.yml`'s `start-runner`/`stop-runner` jobs handle the
VM's lifecycle per CI run. If a run's `start-runner` step fails (Azure
outage, expired federation, whatever), every job that needs the runner
queues rather than fails outright — same tradeoff Option A (the laptop)
would have had, not worth building automatic failover for.

**2026-08-25 addendum**: originally only the 3 heaviest Compose jobs ran
here; now every job does except `changes`/`start-runner`/`stop-runner`
themselves (structurally irreducible — something has to decide to turn
the VM on and then do it, and that can't run on the VM being turned on).
Widened after this repo's GitHub Actions minutes were fully exhausted for
real, which blocks *every* `ubuntu-latest` job outright, not just the
expensive ones — see `docs/design/2026-08-25-self-hosted-ci-runners.md`'s
own addendum for the incident. One real consequence worth knowing before
relying on this: a single runner processes one job at a time, so jobs
that used to run in GitHub-hosted parallel now serialize on this one VM
— a real-code push's total CI wall-clock time went up accordingly, in
exchange for using close to zero GitHub-hosted minutes per run instead of
all of them.

## Before this repo goes public

Decommission or fork-restrict `canopica-heavy` first — self-hosted
runners on a repo that accepts fork PRs are a known arbitrary-code-
execution vector (design doc §5). `terraform destroy` from this directory
removes everything provisioned here.

## Cost

Not free — this VM's size isn't covered by any Azure free-tier
allowance. Billed only for actual `az vm start` uptime plus the OS disk
at rest; design doc §5 has the honest range given this project's real
push cadence (roughly $20-50/month, not "a few dollars," if most
iteration isn't happening locally first — see that section for why local
repro before push is what actually controls this number).

## Tearing down

```
terraform destroy
```

Also manually revoke the runner registration if `destroy` doesn't reach
GitHub's side cleanly (Settings → Actions → Runners → remove
`canopica-heavy`) — a registered runner pointing at a deleted VM is
inert but worth cleaning up rather than leaving stale.
