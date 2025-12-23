variable "name" { type = string }
variable "bucket_arn" { type = string }

data "aws_iam_policy_document" "assume" {
  statement {
    effect = "Allow"
    principals { type = "Service", identifiers = ["ec2.amazonaws.com"] }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "runner" {
  name               = var.name
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "policy" {
  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListBucket",
      "s3:GetObject"
    ]
    resources = [
      var.bucket_arn,
      "${var.bucket_arn}/*"
    ]
  }
}

resource "aws_iam_role_policy" "inline" {
  name   = "${var.name}-artifacts"
  role   = aws_iam_role.runner.id
  policy = data.aws_iam_policy_document.policy.json
}

output "role_arn" { value = aws_iam_role.runner.arn }
