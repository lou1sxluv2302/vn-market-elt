---
name: security-audit
description: Run the read-only security audit of vn-market-elt and its private companion — secrets across every git object, ignore rules, public-content leaks, dependencies, CI and infrastructure. Use before a repository's first push, before every release tag, after an incident, monthly, or when asked to audit or check security.
---

# security-audit

The procedure is `docs/runbooks/security-audit.md`. This skill only sequences it;
when the two differ, the runbook wins.

1. **Read-only.** Change nothing, rewrite no history, rotate nothing, call no external service until the owner approves fixes.
   Done when you have stated this mode to the owner.

2. **Inventory.** For each repository: `git for-each-ref`, reflog, stash, `git fsck --unreachable --no-reflogs`.
   Done when every ref and unreachable commit is listed.

3. **Scan.** `python tools/secret_scan.py --repo <path>` for each repository. Locations are in `CLAUDE.local.md`.
   Done when each scan's exit code is recorded.

4. **Checklist.** Mark every item of the runbook's scope checklist ✅ · 🔴 · ⚪ (not applicable or not assessed, with the reason).
   Done when no item is unmarked.

5. **Report** in the runbook's format, in the conversation. Never show more than four characters at each end of a value.
   Done when the owner has the report.

6. **Record.** Write the findings to the private repository as `docs/audits/<date>-<reason>.md`. Findings never go into this public repository.
   Done when the file is committed there.

7. **After approved fixes**, rerun step 3.
   Done when every scan exits 0 and the record states what was fixed.
