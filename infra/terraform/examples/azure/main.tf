provider "azurerm" { features {} }

module "artifacts" {
  source              = "../../modules/azure_artifact_store"
  name                = var.storage_account_name
  resource_group_name = var.resource_group_name
}

module "identity" {
  source              = "../../modules/azure_runtime_identity"
  name                = var.identity_name
  resource_group_name = var.resource_group_name
}

output "artifact_store_uri" { value = "azblob://${module.artifacts.container_name}@${module.artifacts.storage_account_name}" }
output "runtime_identity" { value = module.identity.client_id }
