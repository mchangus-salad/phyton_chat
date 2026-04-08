terraform {
  required_version = ">= 1.7.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state backend – populated automatically by deploy.ps1.
  # Once created, the state lives in an Azure Storage Account.
  # backend "azurerm" {}
}

provider "azurerm" {
  features {}
}
