terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

module "artifact_store" {
  source      = "../../modules/aws_s3_artifact_store"
  bucket_name = var.bucket_name
}
