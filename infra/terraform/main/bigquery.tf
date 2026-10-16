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

# S2 (ADR-0031): one row per feed message, loaded batch by batch by the uploader as
# sa-collector. Columns are the collector's parquet schema. Partitioned by day on
# received_at (a session's Vietnam and UTC dates coincide: 01:55-08:05 UTC); a partition
# filter is required so a hot-path view that forgets "today" fails instead of scanning
# every day. No expiration: raw stream data cannot be re-captured (spec §14.8).
resource "google_bigquery_table" "stream_messages" {
  dataset_id  = google_bigquery_dataset.this["raw_vps_stream"].dataset_id
  table_id    = "messages"
  description = "Verbatim feed messages, one row each; loaded per 60-second batch."
  labels      = merge(local.labels, { component = "warehouse" })

  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "received_at"
  }
  require_partition_filter = true

  schema = jsonencode([
    { name = "payload", type = "STRING", mode = "NULLABLE", description = "The message as received; binary messages decoded with replacement." },
    { name = "is_binary", type = "BOOLEAN", mode = "NULLABLE", description = "The message arrived as bytes." },
    { name = "received_at", type = "TIMESTAMP", mode = "NULLABLE", description = "When the collector received it (UTC, milliseconds)." },
    { name = "batch_id", type = "STRING", mode = "NULLABLE", description = "Window start (Vietnam time) and the collector run, e.g. 20261019T090000-085500." },
    { name = "seq", type = "INTEGER", mode = "NULLABLE", description = "Order within the batch." },
  ])
}
