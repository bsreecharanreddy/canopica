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
  description = "Sized to what infra/docker-compose.yml's opensearch+ollama+api actually need, not guessed -- see design doc §2's measured OpenSearch (2GB heap) and Ollama (~3GB resident models) figures; either family below roughly matches the ~7.65GB Docker VM this project's own dev machine already runs the same stack on. D2s_v7, not B2ms or D2s_v5: both came back NotAvailableForSubscription in centralus too (confirmed via a full `az vm list-skus --location centralus --all` dump, not just the one SKU tried each time) -- this is a subscription-level family restriction on new/free-trial Azure subscriptions, not a per-region capacity issue as first assumed when eastus->centralus didn't fix it. `Standard Dsv7 Family` came back with restrictions: [] and 4/4 vCPU quota free (`az vm list-usage --location centralus`), so D2s_v7 (2 vCPU, 8GB RAM, same shape as the other two) is the first size in this search that's actually usable on this subscription."
  type        = string
  default     = "Standard_D2s_v7"
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
