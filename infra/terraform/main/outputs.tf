# Values the CI workflow needs; store them as GitHub Actions repository
# variables, not in the repository.

output "wif_provider" {
  description = "GitHub variable GCP_WIF_PROVIDER."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "ci_service_account" {
  description = "GitHub variable GCP_CI_SERVICE_ACCOUNT."
  value       = google_service_account.this["sa-ci-plan"].email
}

output "raw_bucket" {
  value = google_storage_bucket.raw.name
}

output "datasets" {
  value = sort([for d in google_bigquery_dataset.this : d.dataset_id])
}

output "collector_vm" {
  value = var.create_vm ? google_compute_instance.collector[0].name : "not created (create_vm = false)"
}
