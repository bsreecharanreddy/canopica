locals {
  name_prefix       = "${var.project_name}-ci-runner"
  github_owner_name = split("/", var.github_repository)[0]
  github_repo_name  = split("/", var.github_repository)[1]
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "this" {
  name     = "${local.name_prefix}-rg"
  location = var.location
  tags     = var.tags
}

# --- Networking: no public IP, no inbound rules ---------------------------
# GitHub's own self-hosted runner agent works by polling GitHub outbound
# over HTTPS -- nothing ever needs to reach this VM from the internet. No
# public IP means there is no internet-routable address for an inbound
# connection to target at all; the NSG (zero custom security_rule blocks,
# relying on Azure's own implicit deny-inbound-from-internet default) is
# defense in depth on top of that, not the only thing preventing inbound
# access. Design doc §5's residual-risk statement depends on this: the
# only attack surface is the standard self-hosted-runner-executes-a-fork-
# PR's-workflow vector, not network exposure.

resource "azurerm_virtual_network" "this" {
  name                = "${local.name_prefix}-vnet"
  address_space       = ["10.60.0.0/24"]
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = var.tags
}

resource "azurerm_subnet" "this" {
  name                 = "${local.name_prefix}-subnet"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.60.0.0/27"]
}

# Found live, not anticipated: without this, the subnet's only outbound
# path is Azure's default platform-provided SNAT, which has a fixed
# ~4-minute idle timeout that cannot be configured. GitHub's runner agent
# holds one long-lived connection to broker.actions.githubusercontent.com
# while waiting for a job; once that connection sits idle past ~4 minutes
# (very plausible between two queued jobs, and observed for real -- run
# `32924144504`'s runner went silently unresponsive after "Listening for
# Jobs", `ss` showed the socket still `ESTAB` locally with zero
# Recv-Q/Send-Q, and only a service restart unstuck it), Azure drops the
# SNAT mapping with no FIN/RST sent to either side -- the connection looks
# alive forever but is actually dead, and nothing here ever logs an error
# for it. A NAT Gateway is outbound-SNAT only, no listener, so it doesn't
# reopen the inbound exposure the "no public IP" design deliberately
# avoids -- it only replaces *how* outbound traffic is source-NATed, with
# a configurable idle timeout instead of the fixed platform default.
#
# COST, and a dated commitment attached to it: this pair (NAT Gateway +
# its Standard public IP) bills ~$36/month *continuously* -- unlike the VM
# it serves, there is no "deallocate between runs" for it. It was
# deliberately left unapplied when first written (2026-08-25) for exactly
# that reason, and applied a day later only once it was established that
# this subscription is an Azure free trial with $200 of credit that
# expires ~30 days from signup and cannot otherwise be spent at this
# project's ~$0.11-per-CI-run burn rate. That makes it effectively free
# *inside the trial window and nowhere else*. The decision on record is
# therefore to destroy it before the trial converts, not to keep it:
# `terraform destroy -target=azurerm_subnet_nat_gateway_association.this
# -target=azurerm_nat_gateway_public_ip_association.this
# -target=azurerm_nat_gateway.this -target=azurerm_public_ip.nat`, after
# which the SNAT idle-timeout bug returns and the workaround is once again
# a manual `systemctl restart` of the runner service. Tracked with its
# deadline in docs/STATUS.md; do not let this comment be the only record.
resource "azurerm_public_ip" "nat" {
  name                = "${local.name_prefix}-nat-pip"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

resource "azurerm_nat_gateway" "this" {
  name                = "${local.name_prefix}-natgw"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku_name            = "Standard"
  # 30 min: comfortably above any realistic gap between one job finishing
  # and the next being dispatched to this single-runner setup, without
  # reaching for the 120-minute ceiling on a resource billed per hour
  # regardless of how idle it is.
  idle_timeout_in_minutes = 30
  tags                    = var.tags
}

resource "azurerm_nat_gateway_public_ip_association" "this" {
  nat_gateway_id       = azurerm_nat_gateway.this.id
  public_ip_address_id = azurerm_public_ip.nat.id
}

resource "azurerm_subnet_nat_gateway_association" "this" {
  subnet_id      = azurerm_subnet.this.id
  nat_gateway_id = azurerm_nat_gateway.this.id
}

resource "azurerm_network_security_group" "this" {
  name                = "${local.name_prefix}-nsg"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = var.tags
  # No security_rule blocks -- see the networking note above.
}

resource "azurerm_network_interface" "this" {
  name                = "${local.name_prefix}-nic"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.this.id
    private_ip_address_allocation = "Dynamic"
    # No public_ip_address_id -- deliberate, see above.
  }
}

resource "azurerm_network_interface_security_group_association" "this" {
  network_interface_id      = azurerm_network_interface.this.id
  network_security_group_id = azurerm_network_security_group.this.id
}

# --- The VM itself ----------------------------------------------------

# Generated rather than supplied -- nothing here is ever reached over SSH
# (no public IP; one-time setup and any future access happen via
# `az vm run-command invoke`, which uses the Azure control plane, not the
# network), so there's no operator key to manage. The private half lives
# only in Terraform state.
resource "tls_private_key" "vm_ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "azurerm_linux_virtual_machine" "this" {
  name                = "${local.name_prefix}-vm"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  size                = var.vm_size
  admin_username      = var.admin_username
  tags                = var.tags

  network_interface_ids = [azurerm_network_interface.this.id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = tls_private_key.vm_ssh.public_key_openssh
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 32
  }

  # Ubuntu 24.04 LTS. Verify against `az vm image list --publisher
  # Canonical --sku ubuntu-24_04-lts --all --output table` before applying
  # if this offer/sku naming has moved on by the time this is run --
  # Canonical has renamed these before.
  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
    admin_username = var.admin_username
  }))

  # Left running after apply -- cloud-init needs a few minutes to finish
  # installing Docker and the runner binary. README.md's one-time
  # registration step confirms cloud-init completed before the operator
  # deallocates it for the first time; Terraform doesn't wait for
  # cloud-init itself; that is intentionally a manual checkpoint, not
  # scripted, per design doc §4's "don't build idle-shutdown machinery"
  # judgment call applied to setup too.
}

# --- GitHub OIDC federation -------------------------------------------
# ci.yml's start-runner/stop-runner jobs authenticate via azure/login
# using this app registration -- no client secret stored in GitHub, ever.
# Two federated credentials because this workflow runs on both `push` to
# main and `pull_request`, and GitHub's OIDC subject claim differs by
# trigger type; a credential trusts one subject pattern each, not a
# wildcard across both.

resource "azuread_application" "ci_runner" {
  display_name = "${local.name_prefix}-github-oidc"
}

resource "azuread_service_principal" "ci_runner" {
  client_id = azuread_application.ci_runner.client_id
}

resource "azuread_application_federated_identity_credential" "main_branch" {
  application_id = azuread_application.ci_runner.id
  display_name   = "github-actions-main"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  # Immutable-ID format (github_owner_id/github_repo_id's own comment has
  # the why), not the plain-name form GitHub's docs lead with -- this repo
  # was renamed after 2026-07-15, so GitHub already emits this format and a
  # plain-name subject here simply never matches.
  subject = "repo:${local.github_owner_name}@${var.github_owner_id}/${local.github_repo_name}@${var.github_repo_id}:ref:refs/heads/main"
}

resource "azuread_application_federated_identity_credential" "pull_request" {
  application_id = azuread_application.ci_runner.id
  display_name   = "github-actions-pull-request"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${local.github_owner_name}@${var.github_owner_id}/${local.github_repo_name}@${var.github_repo_id}:pull_request"
}

# Virtual Machine Contributor, not plain Contributor -- ci.yml's
# start-runner/stop-runner jobs only ever need to start/deallocate this
# one VM, never create, delete, or reconfigure anything in this resource
# group. Scoped to the resource group (not the subscription) for the same
# least-privilege reason.
resource "azurerm_role_assignment" "ci_runner_vm_contributor" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Virtual Machine Contributor"
  principal_id         = azuread_service_principal.ci_runner.object_id
}
