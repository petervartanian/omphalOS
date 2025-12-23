variable "name" { type = string }
variable "kms_key_arn" { type = string, default = "" }
variable "retention_days" { type = number, default = 90 }

resource "aws_s3_bucket" "artifacts" {
  bucket = var.name
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "v" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "sse" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn == "" ? "AES256" : "aws:kms"
      kms_master_key_id = var.kms_key_arn == "" ? null : var.kms_key_arn
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "lc" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    id     = "retention"
    status = "Enabled"
    expiration { days = var.retention_days }
    noncurrent_version_expiration { noncurrent_days = var.retention_days }
  }
}

output "bucket_name" { value = aws_s3_bucket.artifacts.bucket }
output "bucket_arn" { value = aws_s3_bucket.artifacts.arn }
