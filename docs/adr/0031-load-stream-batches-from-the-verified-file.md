# ADR-0031: S2 - load each stream batch from the verified local file, exactly once

- Status: Accepted
- Date: 2026-10-17
- Spec: S2 (amends "load job GCS →"), §14.2

## Context

Spec S2 planned a BigQuery load job from GCS after each batch. The job would run as
`sa-collector`, which holds `storage.objectCreator` on the raw bucket (ADR-0030): it
cannot read objects, so a load from `gs://` would be refused. A session is ~370 batches.
BigQuery's documented defaults (checked 2026-10-17): 1,500 load jobs per table per day,
failed ones included, not raisable; 30,000 partition modifications per day on a
column-partitioned table; load jobs are not billed.

## Decision

1. The uploader loads each batch from the same local file whose bytes it has just verified
   against the stored object (size and CRC32C). GCS stays the archive the warehouse can be
   rebuilt from; the collector's account gains no read access.
2. One load job per batch into `raw_vps_stream.messages`, partitioned by day on
   `received_at`, partition filter required, no expiration. The job id is derived from the
   batch and an attempt number kept in a marker next to the file: a load retried after a
   timeout finds its own job instead of appending again, and a new attempt starts only once
   the previous job is known to have failed.
3. A batch is done when the job's `output_rows` equals the file's rows; otherwise the file
   goes to `conflict/` for a person. The object carries its message count as metadata, and
   `tools/reconcile_stream.py --date D` compares GCS and BigQuery per batch once a day.
4. The owner may impersonate `sa-collector` (Token Creator), so the uploader can run on the
   owner's machine when the collector does (S2.4, or local collection after the S0 gate).

## Rejected

- Granting `sa-collector` `objectViewer` and loading from `gs://`: read access to every raw
  object for the account on the exposed VM.
- The Storage Write API: billed per GB, and stateful.
- An external table over GCS: every hot-path refresh would scan parquet files.

## Consequences

- ~370 of the 1,500 daily load jobs per table: a quarter of a limit that cannot be raised,
  with room for retries. Subscribing to many more symbols changes the size of a batch, not
  the number of jobs.
