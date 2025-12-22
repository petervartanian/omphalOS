terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

resource "google_storage_bucket" "artifacts" {
  name                        = var.bucket_name
  location                    = var.location
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
}

output "bucket_name" {
  value = google_storage_bucket.artifacts.name
}
