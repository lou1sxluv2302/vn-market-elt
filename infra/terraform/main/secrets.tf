# Container only. The owner adds the value once, in S1, with
#   gcloud secrets versions add vnstock-api-key --data-file=-
# so the key never passes through Terraform state.
resource "google_secret_manager_secret" "vnstock_api_key" {
  secret_id = "vnstock-api-key"
  labels    = merge(local.labels, { component = "collector" })

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "collector_reads_key" {
  secret_id = google_secret_manager_secret.vnstock_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.this["sa-collector"].member
}
