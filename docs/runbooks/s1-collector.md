# Runbook - S1 collector

Two processes (ADR-0030): `stream_collector` writes one parquet file per 60-second window
into a local spool; `uploader` moves the spool to the raw bucket, deleting a file only when
the stored object's size and CRC32C match. Deployment (systemd on the VM, or a local
service) follows the S0 gate; until then both run by hand.

## Run by hand

The collector needs the licensed feed library, so it runs under the interpreter that holds
it, with this package on the path. Start it from a folder outside every repository: the
library writes its own `AGENTS.md` into the working directory.

```powershell
Set-Location "$env:USERPROFILE"
$env:PYTHONPATH = "<this repo>\src"
& "<venv with the feed library>\Scripts\python.exe" -m vnmarket.collector.stream_collector `
  --symbols-file universe.txt --spool "<this repo>\data\collector\spool"
```

It stops at `schedule.stop_local` (config/collector.yml) or `--until HH:MM`; on a day the
holiday seed marks `confirmed` it exits 3 without connecting.

```powershell
.\.venv\Scripts\python.exe -m vnmarket.collector.uploader --until 15:05   # or --once
```

Off the VM the uploader impersonates `collector.service_account` (config/env/prod.yml);
the owner needs Token Creator on that account. Exit 1 means files are left in the spool
or moved to `data/collector/conflict/` - read the `upload_failed`, `verify_failed` and
`batch_conflict` lines; nothing there is ever deleted automatically.

## Checked

- Self-tests: `python -m vnmarket.collector.stream_collector --self-test`, same for
  `uploader` (both in CI).
- 2026-10-16 23:40 (market closed), 2 minutes, 3 symbols: connected, one batch of one
  status message, exit 0. The upload to the bucket is first exercised at S1.4.
