# Security policy

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's
[private vulnerability reporting](../../security/advisories/new) for this
repository. You will get an acknowledgement within 7 days.

## What this repository will never contain

- **Credentials** of any kind: API keys, tokens, passwords, service-account key
  files. GCP access is keyless (attached service accounts, application-default
  credentials, Workload Identity Federation).
- **Market data.** The data vendors used here do not allow redistribution. Only
  synthetic fixtures live in `tests/fixtures/`; dashboards and screenshots in
  docs use synthetic data.
- **Environment identifiers** such as the GCP project id or bucket names - they
  live in git-ignored `config/env/*.yml`; only `*.example.yml` is committed.
- **Personal or work e-mail addresses.** Commits use the GitHub noreply address.

## Controls

| Layer | Control |
|---|---|
| Commit | pre-commit: gitleaks, data-file and size blocks |
| Push | GitHub secret scanning with push protection |
| Pull request | Required checks: gitleaks on the diff, data-file block, lint, self-tests |
| Weekly | gitleaks over the full history · `pip-audit` · Dependabot security updates (as advisories appear; routine version bumps are off) |
| Before every tag | Full review: history scan, no data files ever committed, no user-managed service-account keys |
| Cloud | Least-privilege service accounts · SSH only through IAP · no public ingress · public access prevention on buckets · audit-log alerts on IAM and firewall changes · budget alerts |

The full design is in [`docs/spec.md` §14](docs/spec.md#14-security).

## If a secret is ever committed

Deleting the file does not remove it from history. **Revoke the secret first**,
then rewrite history, then force-push with the ruleset temporarily relaxed, and
record the incident in `docs/runbooks/`.
