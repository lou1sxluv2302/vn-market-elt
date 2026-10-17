# ADR-0032: S1.4 - the stale-feed alert watches a custom metric the uploader writes

- Status: Accepted
- Date: 2026-10-17
- Spec: S1 (alert); amends ADR-0030 decision 3

## Context

ADR-0030 put the 3-minute alert in Cloud Monitoring, counting the uploader's
`batch_uploaded` log lines through a log-based metric. Those lines reach Cloud Logging only
through an agent (the Ops Agent on a VM, a log shipper elsewhere), so the alert would depend
on where the S0 gate puts the collector. `sa-collector` already holds
`monitoring.metricWriter`. Cloud Monitoring has no schedule for a policy (snoozes only).

## Decision

1. After each loaded batch the uploader writes one point of the gauge
   `custom.googleapis.com/vnmarket/stream_batches_loaded` (the batch's messages), at most
   one per 10 s; a failed write is logged and never holds a batch back. Same code and same
   permission on every host.
2. One PromQL alert policy: the metric absent for `stale_alert_minutes` **and** the time
   inside a trading window **and** Monday-Friday **unless** a confirmed holiday of the seed.
   Windows (Vietnam time) and the grace period live in `config/collector.yml`, which
   Terraform reads; holidays come from `dbt/seeds/holidays.csv`. One place each.
3. Windows: 09:05-11:30 and 13:03-14:45. Lunch and the time after 14:45 never alert; the
   first minutes after each start are grace, to be measured in S1.6.

Tried 2026-10-17 against the live metric through the Prometheus query API, with the exact
query Terraform generated: silent on a Saturday (control); the same query widened to
Saturday and the current time fired after 3 silent minutes (planted); that planted query
with today added as a holiday was silent again. `hour()`, `minute()`, `day_of_week()` and
date matching work and use UTC; the selector needs `monitored_resource="global"`.

## Consequences

- Cost: alerting is free today; from 2027-09-01 at the earliest, $0.35 a month per metric
  referenced (one). The metric stays far inside the free 150 MiB a month.
- An announced or provisional holiday raises one e-mail (the collector runs those days).
- A seed change takes effect at the next `terraform apply`.
