terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state backend – populated automatically by deploy.ps1.
  # Once created, state lives in a GCS bucket.
  # backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}
