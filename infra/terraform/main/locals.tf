locals {
  labels = {
    project    = "vn-market-elt"
    env        = "prod"
    managed_by = "terraform"
  }

  state_bucket = "${var.project_id}-tfstate"

  # Spec §13.4: one dataset per layer.
  datasets = {
    raw_vps_stream = "Raw intraday records from the VPS stream, append-only."
    raw_vnstock    = "Raw daily records loaded by dlt from vnstock, append-only."
    staging        = "dbt staging models: renamed, typed, deduplicated."
    intermediate   = "dbt intermediate models."
    marts_intraday = "dbt marts for the hot path (views)."
    marts_daily    = "dbt marts for the cold path."
  }

  # Spec §14.2. Keys are the account ids (sa-<role>).
  service_accounts = {
    "sa-collector" = "Collector on the VM: writes raw stream batches."
    "sa-dbt"       = "dbt runs: reads raw, writes staging, intermediate and marts."
    "sa-bi-reader" = "Reserved for a future BI tool: reads marts only."
    "sa-ci-plan"   = "GitHub Actions through WIF: read-only, enough for terraform plan."
  }

  # Resource-scoped dataset roles: dataset => { account => role }.
  dataset_roles = {
    raw_vps_stream = { "sa-collector" = "roles/bigquery.dataEditor", "sa-dbt" = "roles/bigquery.dataViewer" }
    raw_vnstock    = { "sa-dbt" = "roles/bigquery.dataViewer" }
    staging        = { "sa-dbt" = "roles/bigquery.dataEditor" }
    intermediate   = { "sa-dbt" = "roles/bigquery.dataEditor" }
    marts_intraday = { "sa-dbt" = "roles/bigquery.dataEditor", "sa-bi-reader" = "roles/bigquery.dataViewer" }
    marts_daily    = { "sa-dbt" = "roles/bigquery.dataEditor", "sa-bi-reader" = "roles/bigquery.dataViewer" }
  }

  dataset_bindings = merge([
    for dataset, grants in local.dataset_roles : {
      for account, role in grants : "${dataset}/${account}" => {
        dataset = dataset
        account = account
        role    = role
      }
    }
  ]...)

  # Project-level roles, only where no narrower scope exists. BigQuery jobs are
  # created in a project, so jobUser cannot be granted on a dataset.
  project_roles = {
    "sa-collector/jobUser"        = { account = "sa-collector", role = "roles/bigquery.jobUser" }
    "sa-dbt/jobUser"              = { account = "sa-dbt", role = "roles/bigquery.jobUser" }
    "sa-bi-reader/jobUser"        = { account = "sa-bi-reader", role = "roles/bigquery.jobUser" }
    "sa-ci-plan/viewer"           = { account = "sa-ci-plan", role = "roles/viewer" }
    "sa-ci-plan/securityReviewer" = { account = "sa-ci-plan", role = "roles/iam.securityReviewer" }
    "sa-collector/logWriter"      = { account = "sa-collector", role = "roles/logging.logWriter" }
    "sa-collector/metricsOut"     = { account = "sa-collector", role = "roles/monitoring.metricWriter" }
  }

  # Spec §14.9: e-mail on these admin-activity events.
  log_alerts = {
    iam-policy-changed = {
      name = "IAM policy changed"
      # Project, service-account, bucket and dataset policies log different method names.
      filter = "logName:\"cloudaudit.googleapis.com%2Factivity\" AND protoPayload.methodName=~\"(?i)setiampolicy|setiampermissions\""
    }
    service-account-key-created = {
      name   = "Service account key created"
      filter = "protoPayload.methodName=\"google.iam.admin.v1.CreateServiceAccountKey\""
    }
    firewall-changed = {
      name   = "Firewall rule changed"
      filter = "resource.type=\"gce_firewall_rule\" AND protoPayload.methodName=~\"compute\\.firewalls\\.(insert|patch|update|delete)\""
    }
  }
}
