# Service accounts never get user-managed keys (D12): the VM uses its attached
# account, local runs use ADC, GitHub Actions uses WIF.
resource "google_service_account" "this" {
  for_each = local.service_accounts

  account_id   = each.key
  display_name = each.key
  description  = each.value
}

resource "google_project_iam_member" "ci_plan" {
  for_each = local.ci_plan_roles

  project = var.project_id
  role    = each.value
  member  = google_service_account.this["sa-ci-plan"].member
}

# The loader runs on the owner's machine (the v1 history lives there) as
# sa-loader: the owner may mint short-lived tokens for it, nobody else may.
resource "google_service_account_iam_member" "owner_impersonates_loader" {
  service_account_id = google_service_account.this["sa-loader"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.owner_email}"
}

# dbt runs on the owner's machine as sa-dbt, the same way (P2).
resource "google_service_account_iam_member" "owner_impersonates_dbt" {
  service_account_id = google_service_account.this["sa-dbt"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.owner_email}"
}

# Reconciliation reads the marts as sa-bi-reader (marts_* only), the same way.
resource "google_service_account_iam_member" "owner_impersonates_bi_reader" {
  service_account_id = google_service_account.this["sa-bi-reader"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.owner_email}"
}

resource "google_project_iam_custom_role" "ci_plan_compute" {
  role_id     = "ciPlanComputeReader"
  title       = "CI plan: compute metadata reader"
  description = "Read compute metadata for terraform plan; no serial-port output."
  permissions = local.ci_plan_compute_permissions
}

resource "google_project_iam_member" "ci_plan_compute" {
  project = var.project_id
  role    = google_project_iam_custom_role.ci_plan_compute.id
  member  = google_service_account.this["sa-ci-plan"].member
}

resource "google_project_iam_member" "this" {
  for_each = local.project_roles

  project = var.project_id
  role    = each.value.role
  member  = google_service_account.this[each.value.account].member
}
