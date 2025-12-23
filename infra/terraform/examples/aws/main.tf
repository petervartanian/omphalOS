provider "aws" { region = var.region }

module "artifacts" {
  source = "../../modules/aws_artifact_store"
  name   = var.bucket_name
}

module "identity" {
  source     = "../../modules/aws_runtime_identity"
  name       = var.role_name
  bucket_arn = module.artifacts.bucket_arn
}

module "logs" {
  source = "../../modules/aws_logging_sink"
  name   = var.log_group_name
}

output "artifact_store_uri" { value = "s3://${module.artifacts.bucket_name}" }
output "runtime_identity" { value = module.identity.role_arn }
output "logging_sink" { value = module.logs.log_group_name }
