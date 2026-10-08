# ADR-0024: Keep research discipline

- Status: Accepted
- Date: 2026-10-08
- Spec: D24

## Context

ADR-0022 drops most of v1's process rules. v1's research rules are different:
they protected conclusions, and v1's record of refuted hypotheses shows what
they catch.

## Decision

Every research hypothesis is registered before it runs, measured against a
random same-session control with `n_eff` for overlapping windows, explored on
2015–2020 only, and confirmed only by forward accumulation. Parameters are
never tuned toward a better result.

## Consequences

Research moves slower and many hypotheses will fail; failures are recorded as
findings in the private research repository.
