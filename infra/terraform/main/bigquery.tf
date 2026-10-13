resource "google_bigquery_dataset" "this" {
  for_each = local.datasets

  dataset_id  = each.key
  description = each.value
  location    = var.bq_location
  labels      = merge(local.labels, { component = "warehouse" })

  delete_contents_on_destroy = false
}

resource "google_bigquery_dataset_iam_member" "this" {
  for_each = local.dataset_bindings

  dataset_id = google_bigquery_dataset.this[each.value.dataset].dataset_id
  role       = each.value.role
  member     = google_service_account.this[each.value.account].member
}
