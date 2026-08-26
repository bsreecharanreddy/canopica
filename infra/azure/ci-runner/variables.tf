variable "project_name" {
  description = "Short, DNS-safe name prefixed onto every resource -- matches ../'s own convention."
  type        = string
  default     = "canopica"
}

variable "location" {
  description = "Azure region. No Azure Government considerations here (see design doc §5's security note -- this VM is decommissioned before any public-facing decision, well before Azure Government would ever be relevant). centralus, not eastus: on first apply, this subscription hit SkuNotAvailable (Capacity Restrictions) for every B-series and D2s_v5 SKU tried in eastus -- a known pattern for new/free-trial subscriptions in high-demand regions. Quota itself was never the issue (az vm list-usage showed 4/4 vCPUs free for the relevant families); this is capacity allocation, a different thing."
  type        = string
  default     = "centralus"
}

variable "vm_size" {
  description = "D4s_v7 (4 vCPU, 16GB RAM), raised from D2s_v7 (2 vCPU, 8GB) on 2026-08-26 after measuring, not guessing: run `32967528722`'s `e2e-ai` failed with 273Mi RAM free and 1.7GB of swap already in use, while `opensearch` (2.276GiB) and `ollama` (2.914GiB) alone sat at 5.19GiB resident for the job's entire lifetime -- this is the Nth distinct symptom of the same undersized-VM root cause in this project's history (ml-commons circuit breaker x2, a gunicorn timeout, an OOM-killed llama-server, and now a plain API request timeout), each previously treated as its own bug because the symptom moves while the cause does not. +$0.018 for a ~45min run (Azure retail pricing API, centralus: D4s_v7 $0.046939/hr vs D2s_v7's $0.02347/hr) -- the same order of magnitude as the 2026-08-26 disk-size decision, and negligible against this trial's credit. Saturates this subscription's entire 4-vCPU `Standard Dsv7 Family` quota (`az vm list-usage`) with zero headroom for a second Dsv7 VM, which is fine for this single-VM setup but worth knowing if a second one is ever needed. D2s_v7's own original justification (D2s_v5/B2ms both came back `NotAvailableForSubscription` in centralus; Dsv7 was the first family confirmed with `restrictions: []`) still applies to the family choice, just not the size within it."
  type        = string
  default     = "Standard_D4s_v7"
}

variable "github_repository" {
  description = "owner/repo this runner and the federated credential trust -- must match exactly what ci.yml's azure/login step authenticates from."
  type        = string
  default     = "bsreecharanreddy/canopica"
}

variable "github_owner_id" {
  description = "Immutable numeric ID of github_repository's owner, required in the federated credential's `subject` below. Found live, not assumed: the first real CI run after this apply failed `azure/login` with AADSTS700213 (no matching federated identity), because GitHub now issues the immutable-ID subject format (`repo:<owner>@<owner_id>/<repo>@<repo_id>:ref:...`) for any repository renamed on or after 2026-07-15 -- this repo was renamed the same day this Terraform root was first applied. Independently verified against `gh api repos/bsreecharanreddy/canopica` (not just trusted from the error message), matching it exactly."
  type        = number
  default     = 283869510
}

variable "github_repo_id" {
  description = "Immutable numeric ID of github_repository itself -- see github_owner_id's own comment for why this pair exists."
  type        = number
  default     = 1341374123
}

variable "admin_username" {
  description = "Linux admin user on the runner VM. SSH is not exposed (no public IP, no inbound NSG rule) -- one-time setup and any future access happen via `az vm run-command invoke`, which doesn't need this account to be reachable over the network."
  type        = string
  default     = "canopicaci"
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default = {
    project    = "canopica"
    managed_by = "terraform"
    purpose    = "ci-runner"
  }
}
