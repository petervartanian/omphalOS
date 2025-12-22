variable "bucket_name" {
  type        = string
  description = "GCS bucket name for omphalOS run artifacts."
}

variable "location" {
  type        = string
  description = "Bucket location/region."
  default     = "US"
}
