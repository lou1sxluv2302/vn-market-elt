---
name: start-step
description: Start planned work in vn-market-elt - locate the step in the plan, check prerequisites, get a plan approved when the work is large, then open its issue and branch. Use when beginning any spec step (0.x, K0.3, P1-P5, S0-S4, X1-X3) or any new piece of work in this repo.
---

# start-step

Sequence only. The rules live in the files named in each step.

1. **Locate the step.** Read `docs/spec.md` §0 Progress, or `gh issue list --milestone "<phase>"` once milestones exist.
   Done when you can state the step ID, its "Done when" line from spec §6, and who does it (🤖 agent / 👤 owner).

2. **Check prerequisites.** Earlier steps it depends on are checked; every 👤 step it needs is named.
   Done when nothing is missing, or the owner has been asked for exactly what is missing.

3. **Size it.** Large work - a new phase or component, a changed decision, anything that edits the spec - gets a plan approved by the owner first:
   - sharpen it with `/grill-with-docs` (it records new terms in `CONTEXT.md` and decisions as ADRs);
   - publish it with `/to-spec`, then split it with `/to-tickets`;
   - work spanning several sessions gets a `/wayfinder` map.

   A small, fully specified step goes straight on.
   Done when the plan is approved, or you have stated why the step is small.

4. **Issue.** Find or open the GitHub issue for the step; its milestone is the phase.
   Done when the issue number is known.

5. **Branch.** From an up-to-date `main`, create `<type>/<phase>-<short-description>` as defined in `CONTRIBUTING.md`.
   Done when you are on the branch and `git status` is clean.

6. **Read before writing.** Open every file the `CLAUDE.md` routing table names for the step's topics.
   Done when each routed file has been read.

While working: `/tdd` for code (red, green, refactor; matches the self-test rule), `/implement` for ticket-driven work, `/codebase-design` for module boundaries, `/diagnosing-bugs` when something fails. When the work is finished, continue with `ship-pr`.
