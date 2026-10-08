# Runbook — security audit

**When:** before the first push of a repository · before every release tag ·
after any incident · at least monthly. **Who:** the agent runs it; the owner
approves every fix.

## Rules of engagement

1. **Read-only until approved.** Report first; change nothing, rewrite no
   history, rotate nothing, contact no external service.
2. **Never display a full secret.** Report type plus at most the first and last
   four characters. Never copy a value into a file, command, log or report.
3. **History counts.** Scan every object, including amended, rebased and
   unreachable commits. A secret deleted later is still exposed; treat any
   committed credential as compromised until rotated.
4. **Nothing is silently fixed or omitted.** Separate confirmed findings from
   suspected risks and false-positive candidates.
5. **A live production secret** stops the display of its surroundings; record
   only its redacted location, mark it Critical, continue without using it.

## Scope checklist

- [ ] All refs: `git for-each-ref`, reflog, stash, `git fsck --unreachable --no-reflogs`
- [ ] Every object: `python tools/secret_scan.py --repo <path>` (exit 1 = secret found)
- [ ] Commit metadata: author and committer e-mail are the GitHub noreply address
- [ ] `.gitignore`: `git check-ignore` on `.dlt/secrets.toml`, `profiles.yml`,
      key files, `*.env`, data files, `CLAUDE.local.md`
- [ ] Public content: nothing from the private research repo; no vendor-internal
      licence or feed details; no local paths, account tiers or identifiers
- [ ] Dependencies: pinned versions, Dependabot, `pip-audit`
- [ ] When present — application code (authn/authz, injection, SSRF/XSS/CSRF,
      file handling, logging of sensitive data, crypto), CI workflows
      (`permissions:`, SHA-pinned actions, OIDC scope), Terraform (IAM scope,
      public access, firewall), containers and build artifacts
- [ ] GitHub settings: secret scanning and push protection on; `main` ruleset
- [ ] Payment integrations: none in this project (record as not applicable)

## Report format

1. Executive summary and a count by severity (Critical · High · Medium · Low).
2. Per finding: severity · confidence (Confirmed/High/Medium/Low) · description
   · location (file:line or commit/ref) · redacted evidence · impact · immediate
   containment · permanent remediation · rotation or history cleanup required.
3. Credentials requiring immediate rotation · evidence to preserve ·
   remediation order · areas not assessed · follow-up tools.

Findings records are **not** stored in this public repository; they live in the
private companion repository under `docs/audits/`.

## Follow-up tools

`gitleaks detect --log-opts="--all"` · `trufflehog git file://.` ·
`detect-secrets scan` · `pip-audit` · `checkov` / `tfsec` (Terraform) ·
`git fsck --unreachable --no-reflogs`.
