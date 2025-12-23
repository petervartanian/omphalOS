variable "name" { type = string }
variable "bucket_name" { type = string }

resource "google_service_account" "runner" {
  account_id   = var.name
  display_name = var.name
}

resource "google_storage_bucket_iam_member" "writer" {
  bucket = var.bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runner.email}"
}

output "service_account_email" { value = google_service_account.runner.email }
