terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "artifact_store" {
  source      = "../../modules/gcp_gcs_artifact_store"
  bucket_name = var.bucket_name
  location    = var.location
}
