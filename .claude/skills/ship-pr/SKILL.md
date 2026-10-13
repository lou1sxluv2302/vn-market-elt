---
name: ship-pr
description: Verify and open a pull request in vn-market-elt - review the diff for leaks, run every check, reconcile the docs, then wait for the owner's go-ahead before pushing. Use before any push, pull request, or "commit and push" in this repo.
---

# ship-pr

Sequence only. Rules: `CONTRIBUTING.md` (commits, PRs), `docs/engineering-rules.md` (checks), `SECURITY.md` (what never enters the repo).

1. **Review the diff.** `git diff main...HEAD --stat`, then each file. Nothing from the private research repo, no market data, no paths or names from `CLAUDE.local.md`, no vendor-internal licence or feed details.
   Done when every changed file has a one-line purpose and none breaks those rules.

2. **Run the checks; record exit codes.**

   | Check | Command | Required when |
   |---|---|---|
   | Secrets, all git objects | `python tools/secret_scan.py` | always |
   | Self-tests | `python <script> --self-test` for every script touched | a script changed |
   | Lint | `ruff check .` | Python changed |
   | dbt | `dbt parse`, later `dbt build` on DuckDB | dbt changed |
   | Hooks | `pre-commit run --all-files` | once installed |

   Report each as ✅ (exit 0) · 🔴 (non-zero) · ⚪ (not run, with the reason). Any 🔴 stops here.
   Done when the table is complete.

3. **Reconcile the docs.**
   - New terms are in `docs/glossary.md`.
   - Constants live in `config/*.yml`.
   - The step's checkbox in spec §0 is updated.
   - `CHANGELOG.md` has an `[Unreleased]` line.
   - A changed decision has an ADR.
   - Relative links resolve.
   - `CLAUDE.md` stays ≤ 80 lines.
   - No em or en dash anywhere; the ASCII `-` only (`CONTRIBUTING.md`, Text style).

   Done when each item is ✅ or ⚪ with a reason.

4. **Commit.** Conventional Commit title, a body that says why, `Refs: #<issue>`, and the co-author line. Confirm `git config user.email` is the noreply address.
   Done when `git log -1` shows it.

5. **Ask.** Give the owner the summary and the check table. Wait for an explicit go-ahead.

6. **Push and open the PR** with the template filled; "How verified" is the check table. Merging is the owner's decision (squash only).
   Done when the PR URL is reported.
