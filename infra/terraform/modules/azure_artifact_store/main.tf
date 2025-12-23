variable "name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string, default = "eastus" }

resource "azurerm_storage_account" "artifacts" {
  name                     = var.name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  allow_nested_items_to_be_public = false
}

resource "azurerm_storage_container" "runs" {
  name                  = "runs"
  storage_account_name  = azurerm_storage_account.artifacts.name
  container_access_type = "private"
}

output "storage_account_name" { value = azurerm_storage_account.artifacts.name }
output "container_name" { value = azurerm_storage_container.runs.name }
