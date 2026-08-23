# Reference only -- Task 10 (Phase 1b). This configuration is written to
# validate/fmt clean and never applied against a live subscription; see
# README.md for why, and for the exact usgovcloud swap this project would
# need if it ever were.

terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.2"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = true
    }
  }

  # Commercial Azure by default -- Azure Government is a physically and
  # logically separate cloud with its own Resource Manager endpoint and AD
  # authority, not a region, so retargeting it is exactly these two lines
  # (design doc §3.7) with nothing else in this configuration changing:
  #
  #   environment   = "usgovernment"
  #   metadata_host = "management.usgovcloudapi.net"
  #
  # Left commented rather than set because Azure Government isn't
  # self-service (README.md explains this project's own constraint here).
}

provider "random" {}
