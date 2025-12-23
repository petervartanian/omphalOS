variable "name" { type = string }
variable "retention_days" { type = number, default = 30 }

resource "aws_cloudwatch_log_group" "lg" {
  name              = var.name
  retention_in_days = var.retention_days
}

output "log_group_name" { value = aws_cloudwatch_log_group.lg.name }
