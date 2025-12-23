provider "google" { project = var.project_id, region = var.region }

module "artifacts" {
  source = "../../modules/gcp_artifact_store"
  name   = var.bucket_name
}

module "identity" {
  source      = "../../modules/gcp_runtime_identity"
  name        = var.service_account_id
  bucket_name = module.artifacts.bucket_name
}

output "artifact_store_uri" { value = "gs://${module.artifacts.bucket_name}" }
output "runtime_identity" { value = module.identity.service_account_email }
