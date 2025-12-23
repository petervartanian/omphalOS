variable "name" { type = string }
variable "resource_group_name" { type = string }

resource "azurerm_user_assigned_identity" "runner" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = "eastus"
}

output "principal_id" { value = azurerm_user_assigned_identity.runner.principal_id }
output "client_id" { value = azurerm_user_assigned_identity.runner.client_id }
