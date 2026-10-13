resource "google_bigquery_dataset" "this" {
  for_each = local.datasets

  dataset_id  = each.key
  description = each.value
  location    = var.bq_location
  labels      = merge(local.labels, { component = "warehouse" })

  delete_contents_on_destroy = false
}

resource "google_bigquery_dataset" "dev" {
  for_each = local.dev_datasets

  dataset_id                  = each.value
  description                 = "dbt dev target; tables expire after ${var.dev_table_expiration_days} days."
  location                    = var.bq_location
  labels                      = merge(local.labels, { env = "dev", component = "warehouse" })
  default_table_expiration_ms = var.dev_table_expiration_days * 24 * 60 * 60 * 1000

  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset_iam_member" "dbt_writes_dev" {
  for_each = local.dev_datasets

  dataset_id = google_bigquery_dataset.dev[each.value].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = google_service_account.this["sa-dbt"].member
}

resource "google_bigquery_dataset_iam_member" "this" {
  for_each = local.dataset_bindings

  dataset_id = google_bigquery_dataset.this[each.value.dataset].dataset_id
  role       = each.value.role
  member     = google_service_account.this[each.value.account].member
}
