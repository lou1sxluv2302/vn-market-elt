resource "google_monitoring_notification_channel" "owner_email" {
  display_name = "Owner e-mail"
  type         = "email"
  user_labels  = merge(local.labels, { component = "monitoring" })
  labels = {
    email_address = var.alert_email
  }
}

# Spec §14.9. Admin-activity audit logs are on by default and free.
resource "google_monitoring_alert_policy" "log_alert" {
  for_each = local.log_alerts

  display_name          = each.value.name
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.owner_email.id]
  user_labels           = merge(local.labels, { component = "monitoring" })

  conditions {
    display_name = each.value.name
    condition_matched_log {
      filter = each.value.filter
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = var.alert_rate_limit
    }
  }

  documentation {
    content   = "A ${lower(each.value.name)} event was logged. If you did not make this change, check the audit log and revoke access first. Expected right after a terraform apply."
    mime_type = "text/markdown"
  }
}
