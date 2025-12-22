variable "resource_group_name" {
  type        = string
  description = "Resource group name."
}

variable "location" {
  type        = string
  description = "Azure region."
  default     = "eastus"
}

variable "storage_account_name" {
  type        = string
  description = "Storage account name (must be globally unique)."
}

variable "container_name" {
  type        = string
  description = "Blob container name for artifacts."
  default     = "omphalos-artifacts"
}
