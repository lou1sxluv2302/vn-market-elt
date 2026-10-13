# Raw landing bucket. No deletion lifecycle: stream samples cannot be
# re-captured (spec §14.8). us-central1 keeps it inside the free tier.
resource "google_storage_bucket" "raw" {
  name     = "${var.project_id}-prod-raw"
  location = var.region
  labels   = merge(local.labels, { component = "raw" })

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "collector_writes_raw" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectCreator"
  member = google_service_account.this["sa-collector"].member
}

# The state bucket belongs to the bootstrap stack; CI may only read it.
resource "google_storage_bucket_iam_member" "ci_reads_state" {
  bucket = local.state_bucket
  role   = "roles/storage.objectViewer"
  member = google_service_account.this["sa-ci-plan"].member
}
