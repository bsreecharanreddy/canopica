locals {
  name_prefix = "${var.project_name}-ci-runner"
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
  subject        = "repo:${var.github_repository}:ref:refs/heads/main"
}

resource "azuread_application_federated_identity_credential" "pull_request" {
  application_id = azuread_application.ci_runner.id
  display_name   = "github-actions-pull-request"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = "repo:${var.github_repository}:pull_request"
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
