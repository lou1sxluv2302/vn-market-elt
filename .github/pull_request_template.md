<!-- Title: Conventional Commit, e.g. `feat(ingest): ...` - squash merge uses it as the commit. -->

## What

## Why

Refs: #

## Deviations

<!-- Where this differs from the spec, issue or an ADR, and why. "None." if none. -->

## How verified

<!-- Command and exit code per check; result symbols as in CONTRIBUTING.md. -->

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
