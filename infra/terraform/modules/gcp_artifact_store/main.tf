variable "name" { type = string }
variable "location" { type = string, default = "US" }
variable "retention_days" { type = number, default = 90 }

resource "google_storage_bucket" "artifacts" {
  name          = var.name
  location      = var.location
  force_destroy = false
  versioning { enabled = true }
  uniform_bucket_level_access = true
  lifecycle_rule {
    action { type = "Delete" }
    condition { age = var.retention_days }
  }
}

output "bucket_name" { value = google_storage_bucket.artifacts.name }
