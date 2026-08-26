# NOT reference-only, unlike ../ -- this configuration is meant to be
# applied for real, by hand, from the operator's own machine with their
# own subscription. See README.md and the design doc
# (docs/design/2026-08-25-self-hosted-ci-runners.md §5) for why this had
# to be a separate Terraform root rather than folded into ../, whose own
# README states its config is never applied.

terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.2"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.9"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Local state, deliberately -- this is a single-operator setup applied
  # from one machine, and a remote backend (Azure Storage) would be
  # over-engineering for that. The real risk local state has -- losing
  # track of what's actually provisioned -- is bounded here because
  # everything this config creates is also independently visible in the
  # Azure portal and in `gh` (the federated credential, the runner
  # itself). Revisit if this ever needs a second operator.
}

provider "azurerm" {
  features {}
}

provider "azuread" {}

provider "tls" {}
