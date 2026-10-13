# ADR-0028: P2 - reconcile by mechanism; v1's liquidity rules kept as provisional config

- Status: Accepted
- Date: 2026-10-13
- Spec: Q4, P2

## Context

Spec Q4 asked the P2 marts to match v1's DuckDB 100%. A read-only survey of v1 showed
where v1 is wrong or cannot be matched: its future calendar (2026-11-24 and every 2027
weekday trading), its source choice (whichever source it fetched that day), its current
rather than point-in-time exchange, and liquidity tiers that were never measured.

## Decision

1. **Q4 redefined.** Exact where v2 means the same as v1: observed calendar sessions,
   price rows and values, `is_stale`. Every deliberate difference is explained row by
   row by its mechanism (`tools/reconcile_v1_marts.py`): the holiday seed, the primary-
   first source choice and its effect on the next row's `is_stale` and on ADV windows,
   an exchange inferred from different prices. Anything unexplained fails.
2. **Liquidity tiers** 100 / 30 / 10 bn VND stay in `dbt_project.yml` as provisional and
   unmeasured, so the universe reproduces v1; the research track measures them.
3. **ADV20** = mean turnover over the 20 previous non-stale rows, insufficient below 15
   (v1's rule); stale sessions are skipped, not counted as zero.
4. **Delisted symbols** without an exchange get one inferred from price ticks, flagged.
5. **No listing-date filter** yet: dates exist for under half the symbols ("has traded"
   stands in). Recorded as open question 20 in `market-microstructure.md`.
6. **dbt unit tests run in CI on dbt-duckdb** from P2 on.
7. **Source choice prefers a clean row** over the primary source when the primary's row
   fails v1's structural checks and the fallback's passes (refines plan decision 1, found
   by the first reconciliation).

## Consequences

- The calendar starts on 2005-01-01 as v1's; weekdays stand in before the first observed
  session (open question 21).
- Reconciliation reads the marts as `sa-bi-reader`; the owner holds Token Creator on it.
- Raising a tier or changing the ADV rule is a config change plus a new reconciliation,
  and a research finding before it is presented as one.
