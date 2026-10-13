output "state_bucket" {
  description = "Pass to the main stack: terraform init -backend-config=\"bucket=<this>\"."
  value       = google_storage_bucket.tfstate.name
}
