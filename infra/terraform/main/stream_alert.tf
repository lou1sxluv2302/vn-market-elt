# S1.4 (ADR-0032): e-mail when no stream batch has been loaded for `stale_alert_minutes`
# inside a trading window. The uploader writes one point of a custom metric per loaded
# batch, from whichever host the collector runs on; this policy watches it from outside.
# Windows, the metric and the grace period come from config/collector.yml; confirmed
# holidays from the dbt seed. PromQL's hour(), minute() and day_of_week() are UTC; tried
# against the live metric 2026-10-17 (a Monday-Friday condition stayed silent on a
# Saturday, the same condition widened to Saturday fired after 3 silent minutes).

locals {
  collector     = yamldecode(file("${path.module}/../../../config/collector.yml"))
  metric_parts  = split("/", local.collector.upload.metric_type)
  stream_metric = "${replace(local.metric_parts[0], ".", "_")}:${join("_", slice(local.metric_parts, 1, length(local.metric_parts)))}"

  alert_windows_utc = [
    for w in local.collector.alert.windows_local : [
      for hm in w :
      tonumber(substr(hm, 0, 2)) * 60 + tonumber(substr(hm, 3, 2)) - local.collector.alert.utc_offset_minutes
    ]
  ]
  confirmed_holidays = [
    for h in csvdecode(file("${path.module}/../../../dbt/seeds/holidays.csv")) : h.holiday_date
    if h.status == "confirmed"
  ]

  stream_stale_query = join(" ", concat(
    [
      "absent_over_time(${local.stream_metric}{monitored_resource=\"global\"}[${local.collector.stale_alert_minutes}m])",
      "and on() (${join(" or ", [for w in local.alert_windows_utc : "(hour() * 60 + minute() >= ${w[0]} < ${w[1]})"])})",
      "and on() (day_of_week() >= 1 <= 5)",
    ],
    [
      for d in local.confirmed_holidays :
      "unless on() (year() == ${tonumber(substr(d, 0, 4))} and on() month() == ${tonumber(substr(d, 5, 2))} and on() day_of_month() == ${tonumber(substr(d, 8, 2))})"
    ],
  ))
}

resource "google_monitoring_alert_policy" "stream_stale" {
  display_name          = "Stream: no batch loaded for ${local.collector.stale_alert_minutes} minutes in trading hours"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.owner_email.id]
  user_labels           = merge(local.labels, { component = "monitoring" })

  conditions {
    display_name = "No stream batch in a trading window"
    condition_prometheus_query_language {
      query               = local.stream_stale_query
      duration            = "0s"
      evaluation_interval = "60s"
      alert_rule          = "StreamStale"
      rule_group          = "vnmarket"
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "No stream batch has been loaded for ${local.collector.stale_alert_minutes} minutes during a trading window. The rest of the session is being lost. Check the collector and the uploader (docs/runbooks/s1-collector.md), then the gap with tools/reconcile_stream.py after the session."
    mime_type = "text/markdown"
  }
}
