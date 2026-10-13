# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues in `lou1sxluv2302/vn-market-elt`.
Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with `--label` / `--state` filters.
- **Comment**: `gh issue comment <number> --body "..."`
- **Labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Every issue belongs to a phase milestone (spec §6) once milestones exist (step 0.6).
Research work is never tracked here; it lives in the private companion repository.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if external PRs should be triaged as feature requests.)_

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue labelled `wayfinder:map` holding
the Notes / Decisions-so-far / Fog body; **child** tickets are sub-issues (or a task
list with `Part of #<map>`), labelled `wayfinder:<type>`. Blocking uses GitHub issue
dependencies, falling back to a `Blocked by: #<n>` line. Claim with
`gh issue edit <n> --add-assignee @me`; resolve with a comment, close, and a pointer
in the map's Decisions-so-far.
