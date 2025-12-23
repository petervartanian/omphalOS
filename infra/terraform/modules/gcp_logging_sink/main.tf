variable "name" { type = string }

resource "google_logging_project_sink" "sink" {
  name        = var.name
  destination = "logging.googleapis.com/projects/${var.name}"
  filter      = ""
}

output "sink_name" { value = google_logging_project_sink.sink.name }
