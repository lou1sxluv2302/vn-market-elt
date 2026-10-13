# Market domain - where the knowledge lives

Knowledge lives in [`knowledge/`](knowledge/README.md) - v2's own source of truth
(ADR-0021). Open the file that matches the question:

| Question touches | Open |
|---|---|
| Exchanges, the HNX→HOSE consolidation, sessions, bands, ticks, lots, T+2, ex-rights, trading calendar, holidays, indices, foreign ownership limits | [`knowledge/market-microstructure.md`](knowledge/market-microstructure.md) |
| vnstock, the VPS stream feed, device licences, rate limits, flow sources, fallbacks | [`knowledge/data-sources.md`](knowledge/data-sources.md) |
| Look-ahead, coverage, units, thresholds, tests that lie, storage and freshness lessons | [`knowledge/data-quality-lessons.md`](knowledge/data-quality-lessons.md) |
| Indicators, flows, BI conventions | Not migrated yet (K0.3). Read v1's knowledge base, read-only, (path in `CLAUDE.local.md`), after checking its label in the private v1 inventory |

Naming of every term: [`../CONTEXT.md`](../CONTEXT.md).

## Rules that bind this repository

These are the domain facts this project's code depends on directly.

- **Intraday comparisons use the feed's `reference_price_vnd`.** Historical
  prices from vnstock are corporate-action **adjusted**; on an ex-rights day
  "change vs. yesterday's adjusted close" is wrong.
- **Prices are integer VND.** Some sources quote thousands of VND (`28.5` =
  28,500 VND); convert at the raw→staging boundary and verify the scale per
  source.
- **Scope is HOSE + HNX.** UPCoM is declared (so tick-size and band lookups
  work) but excluded from the universe. **From 2026-12-28 every HNX-listed stock
  trades on HOSE** (VNX, announced 2026-09-30): `exchange` is time-varying per
  symbol, and band and tick lookups go by (exchange, date). Details in
  `knowledge/market-microstructure.md`.
- **Stale sessions** (volume = 0, copied price) carry `is_stale = true` and are
  excluded from every calculation, not just flagged.
- **Point-in-time.** Rolling liquidity windows exclude the current session.
- **Delisted symbols stay** - dropping them is survivorship bias.
