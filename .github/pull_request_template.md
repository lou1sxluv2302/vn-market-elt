## What

## Why

Refs #

## How verified

<!-- Command and exit code for each check; a skipped check is ⚪, never ✅. -->

| Check | Result |
|---|---|
| `python tools/secret_scan.py` | |
| `pre-commit run --all-files` | |
| Self-tests of changed scripts | |

## Checklist

- [ ] No real data, secrets, project ids or e-mail addresses (`SECURITY.md`)
- [ ] New terms are in `CONTEXT.md`
- [ ] Every outbound call has a timeout
- [ ] New computing scripts have `--self-test` with planted faults
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
