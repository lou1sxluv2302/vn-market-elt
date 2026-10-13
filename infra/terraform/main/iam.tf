# Service accounts never get user-managed keys (D12): the VM uses its attached
# account, local runs use ADC, GitHub Actions uses WIF.
resource "google_service_account" "this" {
  for_each = local.service_accounts

  account_id   = each.key
  display_name = each.key
  description  = each.value
}

resource "google_project_iam_member" "this" {
  for_each = local.project_roles

  project = var.project_id
  role    = each.value.role
  member  = google_service_account.this[each.value.account].member
}
