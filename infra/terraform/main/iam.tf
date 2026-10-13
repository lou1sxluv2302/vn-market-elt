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
