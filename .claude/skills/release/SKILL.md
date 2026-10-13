---
name: release
description: Cut a SemVer release of vn-market-elt — security audit, changelog with phase measurements, annotated tag and GitHub release.
disable-model-invocation: true
---

# release

Sequence only. Versions and release notes: `CONTRIBUTING.md` (Tags and releases).

1. **Phase complete.** Every "Done when" of the phase in spec §6 has evidence: exit codes, measurements, owner confirmations.
   Done when each line has its evidence; otherwise stop and report what is missing.

2. **Audit.** Run `security-audit`.
   Done when no Critical or High finding is open.

3. **Changelog.** Pick the version from the tag table in `CONTRIBUTING.md`. Move `[Unreleased]` to `[X.Y.Z] — <date>`. Add the phase's **Measurements**, and **Upgrade notes** if a schema changed.
   Done when the changelog PR is open through `ship-pr`.

4. **Merge.** The owner merges the changelog PR.
   Done when `main` contains it.

5. **Tag and publish** after the owner's go-ahead:
   - `git tag -a vX.Y.Z -m "<phase summary>"` on `main`, then push the tag;
   - `gh release create vX.Y.Z` with **Highlights · Changes · Measurements · Upgrade notes**.

   Done when the release URL is reported.

6. **Close out.** Close the phase milestone and update spec §0.
   Done when both are visible on `main` and GitHub.
