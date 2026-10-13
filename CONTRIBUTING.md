# Contributing

This is a solo learning project, but it is run like a team project: every change
goes through a pull request, every release is tagged, and the history is meant
to be read. This file is the **single source** for the Git workflow.

## Agent tooling

- Workflow skills for this repo live in `.claude/skills/` (`start-step`, `ship-pr`,
  `security-audit`, `release`, `harvest-knowledge`).
- They call the engineering skills of [mattpocock/skills](https://github.com/mattpocock/skills)
  (`grill-with-docs`, `to-spec`, `to-tickets`, `wayfinder`, `tdd`, `implement`,
  `code-review`, `diagnosing-bugs`, `domain-modeling`, `triage`). Install those at
  user level; they are not vendored here. Their per-repo configuration is `docs/agents/`.
- A guardrail hook (`.claude/settings.json`, Bash and PowerShell tools) blocks these
  git commands for agents, and the owner runs them: `push` (any form, including
  `git -C <dir> push`), `reset --hard`, `clean` with `-f`/`--force`, `branch -D` /
  `--delete --force`, `checkout .` / `checkout -- .` / `restore .`. Implementation and
  tests: `.claude/hooks/`. This list is the single description of the guardrail.

## Branches - GitHub Flow

```
main ───●──────────●────────────●──────────●──── protected · always deployable · every tag lives here
         \        / \          / \        /
          feat/p0-repo-scaffold   feat/s0-feed-probe   fix/s1-reconnect-backoff
```

- **One long-lived branch: `main`.** No `develop` - with one contributor a second
  long-lived branch adds merges, not safety. Safety comes from the `main`
  ruleset, CI, and tag-pinned deployments.
- Short-lived branches: `<type>/<phase>-<short-description>`, live **≤ 3 days**,
  deleted after merge.

| `<type>` | Use for | Example |
|---|---|---|
| `feat` | New capability | `feat/s1-stream-collector` |
| `fix` | Bug fix | `fix/s1-reconnect-backoff` |
| `infra` | Terraform, systemd, VM | `infra/p0-iap-firewall` |
| `dbt` | Models, tests, seeds | `dbt/s3-intraday-breadth` |
| `docs` | Documentation, ADRs | `docs/p0-adr-0017-tag-pinned-deploy` |
| `ci` | GitHub Actions | `ci/p0-gitleaks-history` |
| `chore` | Dependencies, housekeeping | `chore/bump-dbt-1-9` |
| `hotfix` | Urgent fix to what runs on the VM | `hotfix/v0.3.1-healthcheck-timezone` |

The very first commit (`chore: bootstrap repository`) goes directly to `main`,
because the ruleset needs a branch to protect. Everything after it goes through
a pull request.

## `main` ruleset

- Pull request required; required status checks grow **phase by phase** - a
  check is only required once it exists:

  | From phase | Required checks added |
  |---|---|
  | P0 | `ci / lint` · `ci / self-test` · `security / gitleaks` · `security / data-files` · `infra / terraform-validate` · `infra / terraform-plan` (only when `infra/terraform/` changes) |
  | S3 | `ci / dbt-parse` (no warehouse connection) |
  | P5 | `ci / dbt-build` (dbt-duckdb on synthetic data) |

- **Squash merge only** ⇒ linear history, one commit per PR.
- No force-push or deletion of `main`; tags `v*` cannot be deleted.
- Conversations must be resolved before merge.
- GitHub does not allow approving your own PR, so no review count is required;
  the PR template's checklist replaces it.

## Commits - Conventional Commits

```
<type>(<scope>): <imperative summary, lower case, no trailing period>

<body: why, not what>

Refs: #<issue>
```

- `type`: `feat` · `fix` · `infra` · `dbt` · `docs` · `ci` · `chore` · `refactor` · `test` · `perf`
- `scope`: `collector` · `el` · `dbt` · `infra` · `bi` · `ci` · `security` · `docs`
- Breaking change: `!` after the type and a `BREAKING CHANGE:` line in the body.
- Examples: `feat(collector): flush parquet batch every 60 seconds` ·
  `fix(collector): back off exponentially on websocket reconnect` ·
  `infra(security): restrict ssh ingress to the iap range`
- PR titles follow the same format - squash merge uses the title as the commit.
- Author e-mail is the GitHub **noreply** address (see `SECURITY.md`).

## Tags and releases - SemVer

Annotated tags (`git tag -a`) on `main` only.

| Tag | Milestone |
|---|---|
| `v0.1.0` | P0 - foundations and baseline security, repository public |
| `v0.2.0` | P1-P3 - cold path matches DuckDB |
| `v0.3.0` | S0 + S1 - cloud gate passed, collector ran 5 sessions |
| `v0.4.0` | S2 + S3 - **hot path live** |
| `v0.5.0` | S4 + P4 |
| **`v1.0.0`** | P5 - main path complete, full security review passed, **demo-ready** |
| `v1.1.0` · `v1.2.0` · `v1.3.0` | X1 Snowflake · X2 Athena · X3 Databricks |
| PATCH | Fixes and hotfixes between milestones |

Before `v1.0.0`: a schema change to a table read by BI or downstream dbt ⇒
**MINOR**; a fix without schema change ⇒ **PATCH**.

Every tag has a **GitHub Release** with: **Highlights** · **Changes** (from
commits) · **Measurements** (latency, message counts, DuckDB match) · **Upgrade
notes** (if a schema changed). `CHANGELOG.md` follows *Keep a Changelog* and is
updated in the PR that precedes the tag. Deployment: `infra/deploy.sh vX.Y.Z`;
rollback = deploy the previous tag.

## Issues, milestones, labels

- One **milestone** per phase (`P0 Foundations`, `P1-P3 Cold path`, …, `X3 Databricks`).
- One **issue** per step; branches and PRs reference it.
- Labels: `type:*` (matches branch types) · `area:*` (matches scopes) ·
  `priority:p0|p1|p2` · `blocked` · `security` · `demo` (worth showing).
- One **GitHub Project** board: Backlog → In progress → In review → Done.

## Text style

Write the ASCII hyphen-minus `-` everywhere: prose, ranges (`P1-P3`,
`2015-2020`), table placeholders. Em and en dashes are rejected by the
`no-typographic-dashes` pre-commit hook.

## Before opening a PR

Use the PR template. In "How verified", give the command and its exit code -
a skipped check is reported as skipped (⚪), never as passed.
