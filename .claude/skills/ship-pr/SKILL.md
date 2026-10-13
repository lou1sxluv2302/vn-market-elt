---
name: ship-pr
description: Verify and open a pull request in vn-market-elt - review the diff for leaks, run every check, reconcile the docs, then hand the push to the owner and open the PR. Use before any push, pull request, or "commit and push" in this repo.
---

# ship-pr

Sequence only. Rules: `CONTRIBUTING.md` (commits, PRs), `docs/engineering-rules.md` (checks), `SECURITY.md` (what never enters the repo).

1. **Review the diff.** `git diff main...HEAD --stat`, then each file. Nothing that `SECURITY.md` (What this repository will never contain) or the public-content item of `docs/runbooks/security-audit.md` excludes.
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
   - New terms are in `CONTEXT.md`.
   - Constants live in `config/*.yml`.
   - The step's checkbox in spec §0 is updated.
   - `CHANGELOG.md` has an `[Unreleased]` line.
   - A changed decision has an ADR.
   - Relative links resolve.
   - `CLAUDE.md` is within its line target (its section "Keeping this file a router").
   - Text style holds (`CONTRIBUTING.md`, Text style).

   Done when each item is ✅ or ⚪ with a reason.

4. **Review.** Run `/code-review` against `main`: the Standards axis uses `CONTRIBUTING.md` and `docs/engineering-rules.md`; the Spec axis uses the issue.
   Done when every finding is fixed or answered in the PR description.

5. **Commit.** Conventional Commit title, a body that says why, `Refs: #<issue>`, and the co-author line. Confirm `git config user.email` is the noreply address.
   Done when `git log -1` shows it.

6. **Hand over the push.** Give the owner the summary, the check table and the exact command, `git push -u origin <branch>`. Agents cannot push (`CONTRIBUTING.md`, Agent tooling).
   Done when the owner reports the push done.

7. **Open the PR.** `gh pr create --body-file` skips GitHub's template, so build the body from it:
   - copy `.github/pull_request_template.md` to a scratch file and fill every section; keep each heading, write "None." where nothing applies;
   - the title is the squash commit (`CONTRIBUTING.md`, Commits); `Refs: #<issue>`, or `Closes #<issue>` when the PR finishes it;
   - "How verified" is the check table from step 2; "Deviations" lists every review finding answered rather than fixed (step 4);
   - add the milestone of the phase and the `type:*` / `area:*` labels.

   Merging is the owner's decision (squash only).
   Done when the PR URL is reported and its body has every heading of the template.
