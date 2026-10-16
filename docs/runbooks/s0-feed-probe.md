# Runbook - S0 feed probe

Spec S0: record the intraday feed for 30 minutes, then aggregate. The probe runs under the
interpreter that holds the feed library and its device licence (the previous system's
virtualenv on this machine), by path; it imports nothing from this package.

## Local run (S0.2)

Start at **09:30 Vietnam time** on a trading day (after the opening auction). Raw messages
go to a folder **outside every repository** and are deleted after the report (vendor terms:
aggregates only).

Run it from a folder outside every repository: the library writes its own `AGENTS.md`
into the current directory when it authenticates.

```powershell
Set-Location "$env:USERPROFILE"
& "<v1 venv>\Scripts\python.exe" "<this repo>\src\vnmarket\collector\feed_probe.py" `
  --minutes 30 --symbols <30 symbols, comma-separated> --out "$env:USERPROFILE\vnm-probe"
```

The symbols are the 30 universe symbols with the highest ADV20 on the latest session.
Exit 0 = messages recorded; 1 = connected but nothing delivered; 2 = the library or its
licence is missing (the library prints its own banner and update notices at import; they
are not errors).

Then:

```powershell
python src\vnmarket\collector\feed_report.py "$env:USERPROFILE\vnm-probe\probe_<stamp>.jsonl" --out summary.json
```

The summary holds counts, sizes, field names per message type and RAM/CPU only - no
values. Delete the raw JSONL afterwards.

## On the VM (S0.4, the gate)

The same two commands on the collector VM over IAP SSH, after the owner has stored the API
key in Secret Manager and run the vendor's installer there. Whether the feed accepts a
connection from the VM's address is the gate's question.
