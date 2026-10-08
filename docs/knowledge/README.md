# Knowledge

Market and data knowledge inherited from v1 (ADR-0021), translated, condensed
and re-checked. **This folder is v2's source of truth**; v1's knowledge base is a
frozen reference. Every fact carries its evidence level and v1 source.

| File | Holds | Phase | Status |
|---|---|---|---|
| [`market-microstructure.md`](market-microstructure.md) | Exchanges, sessions, bands, ticks, ex-rights, calendar and holidays, HNX→HOSE consolidation | K0.2 | Written 2026-10-08 |
| [`data-sources.md`](data-sources.md) | vnstock, the VPS stream, flow sources, fallbacks and their traps | K0.2 | Written 2026-10-08 |
| [`data-quality-lessons.md`](data-quality-lessons.md) | 45 lessons from v1 incidents, each mapped to a v2 mechanism | K0.2 | Written 2026-10-08 |
| `indicators.md` | Indicator formulas, incremental EMA, back-adjustment | K0.3 (S3/P2) | Not yet |
| `flows.md` | Foreign and proprietary flow measures, breadth | K0.3 (S3) | Not yet |
| `bi-conventions.md` | Power BI conventions, colour rules, time intelligence by session | K0.3 (S3) | Not yet |

The v1 inventory and v1's research findings are kept in the private research
repository. Engineering rules are not knowledge; they live in [`../engineering-rules.md`](../engineering-rules.md).
