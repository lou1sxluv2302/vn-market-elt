# ADR-0030: S1 - collector and uploader as two processes; the stale-feed alert from outside

- Status: Accepted; decision 3 amended by [ADR-0032](0032-stale-feed-alert-from-a-custom-metric.md) (a custom metric, not a log-based one)
- Date: 2026-10-16
- Spec: S1 (amends the `healthcheck.py` line), §14.4

## Context

Spec S1 planned a `healthcheck.py` on the collector's machine that emails after 3 minutes
without a message, and its planted fault cuts that machine's network for 5 minutes. A script
on the machine whose network is cut cannot send the email that fault expects, and sending
mail from it would need an SMTP password - a new secret. Where the collector runs is
decided by the S0 gate (Monday 2026-10-19); what it does is not.

## Decision

1. `stream_collector.py` writes every message verbatim into one parquet file per 60-second
   window in a local spool, atomically; `uploader.py`, a separate process, moves the spool
   to the raw bucket. A slow or failing upload never stalls collection.
2. A spool file is deleted only when the size and CRC32C the bucket reports for the stored
   object match the local file. The reported values come with the upload's response, so the
   collector's account keeps `objectCreator` only. A name already taken is read back; if it
   differs, or cannot be read, the file goes to `conflict/` - never overwritten or deleted.
3. The 3-minute alert comes from Cloud Monitoring, outside the collector's machine: a
   log-based metric counts the uploader's `batch_uploaded` lines and an alert policy,
   restricted to trading hours, emails the owner when none arrives for 3 minutes (S1.4,
   after the gate). No `healthcheck.py`, no SMTP secret.
4. Calendar: only holidays the seed marks `confirmed` are skipped; `announced` and
   `provisional` dates run (a missed session is lost for good; an unneeded run costs one
   warning). File names carry the collector's start time, so a restart within a minute
   never reuses a name.

## Consequences

- The alert needs the batch log lines to reach Cloud Logging (the Ops Agent on a VM, or a
  log shipper on another host) - part of S1.4 for whichever host the gate picks.
- The collector's account cannot read the bucket: an upload interrupted between the write
  and the local delete ends in `conflict/` for a person to look at, rather than an automatic
  comparison.
