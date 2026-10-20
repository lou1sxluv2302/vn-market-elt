# ADR-0033: S0 cloud gate - passed; the collector runs on the cloud VM

- Status: Accepted
- Date: 2026-10-20
- Spec: S0 gate (S0.3-S0.4), D6, ADR-0006, ADR-0027

## Context

The spec made the cloud collector conditional: if the feed refused a connection from a
Google Cloud address, the collector would move to a Vietnam-hosted VPS or to the owner's
machine. The local probe (2026-10-19, `docs/reports/s0-feed-probe.md`) proved the feed and
sized it; it could not answer the cloud question.

## Decision

The gate is passed. The same probe ran on `collector-prod-01` (e2-micro, us-central1) for 30
minutes of the 2026-10-20 morning session, started by a one-shot systemd timer at 09:30
Vietnam time:

| | VM, 2026-10-20 | Local, 2026-10-19 |
|---|---|---|
| Messages | 86,909 in 31 min; mean 2,804 / min, peak 3,248 | 102,325; mean 3,301, peak 4,241 |
| Silent minutes · disconnects | 0 · 0 | 0 · 0 |
| Latency, server time to receipt (NTP-synced clock) | median 0.6-1.2 s by message type, p99 under 2 s | about 1 s (clock not checked) |
| Process | 142 MB RAM peak, 0.6 % CPU | 183 MB, 0.7 % |

The collector (S1) therefore runs on the VM. The lower rate on the VM is a different
session, not a loss: 0 silent minutes and 0 disconnects, the same message types.

## Consequences

- S1.5 deploys the collector and uploader to the VM (systemd, tagged releases, D17) and adds
  an instance schedule so the VM runs only around trading hours (its public IPv4 is billed
  by the hour).
- One Linux device slot of the vendor licence is used by the VM (the owner's device page,
  2026-10-19: 2 Linux slots, then free).
- The raw recordings were deleted after aggregation, as the S0 plan requires.
