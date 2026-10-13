# Indicators - price, volume, liquidity and market-level measures

Status: K0.3 translation of v1 KB rows labelled for this file in v1's knowledge inventory · Written 2026-10-13. Formulas for ATR, Ichimoku and RSI/MACD reading are deferred to the phase that displays them.

**Evidence tags.** ✅ verified · ⚠️ documentation, industry convention or a derivation not tested in v1 · ❓ unverified or never measured (no number is given) · `measured on v1, <date>` with its population. **Source refs.** `(v1 04 §2, L24)` = v1 KB file `04_technical_analysis.md`, section, line. Other v1 files: `01` market microstructure, `03` data architecture, `05` flows and sentiment, `07` decision engine, `kpi` = `_tham_khao/2026-08-16_kpi_chart_phan_tich_CK_VN.md`, `plan` = v1's master plan, `cfg` = v1's indicator config.

**Conventions.** Prices are integer VND (`_vnd`); volumes are matched board-lot quantities (`match_qty`), never put-through ([market-microstructure.md §2](market-microstructure.md#2-trading-sessions)). Every window counts trading sessions by `session_seq`, never calendar days. Sessions with `is_stale = true` are excluded from every calculation. Terms are defined in [`../../CONTEXT.md`](../../CONTEXT.md).

---

## 1. Defaults

- **Use industry-standard parameters.** Change one only with out-of-sample evidence from at least three distinct market phases; that evidence lives in the private research repository, not here. ⚠️ v1 convention (v1 04 §11, L634)
- **Ship one indicator per measured quantity.** When a candidate is highly correlated with an indicator already shipped, keep the existing one; the cut-off is ❓ (v1 wrote one without measuring it). RSI, MFI and Stochastic measure the same thing: ship one of them. ⚠️ v1 convention (v1 04 §11, L633)
- **Describe every indicator column in one plain sentence** in the dbt docs; a column that cannot be described that way is not shipped. ⚠️ v1 convention (v1 04 §11, L635)
- Industry parameters ⚠️ (v1 kpi Layer 2, L73; v1 04 §2, L33):

| Indicator | Parameters | Chart |
|---|---|---|
| SMA / EMA | 20, 50, 100, 200 | line overlay on candlesticks |
| OHLCV | - | candlesticks + volume bars, on adjusted prices |
| RSI · Stochastic · ROC · ADX/DMI | 14 | oscillator panel below price |
| MACD | 12 / 26 / 9 | histogram + signal line panel |
| Bollinger Bands | 20, 2σ | band overlay |
| ATR, historical volatility | 14 | line panel |
| OBV · MFI · VWAP | MFI 14 | line or overlay |
| Ichimoku (if shown) | 9 / 26 / 52, unchanged | cloud overlay |
| Relative strength vs VN-Index | ratio line | line panel |

- **Price-based charts and indicators use adjusted prices**; on raw prices every moving average breaks at each ex-rights date. ⚠️ (v1 04 header, L4-6; v1 kpi L76)
- **Flag limit-locked sessions on oscillator charts.** A session pinned at the ceiling or floor truncates the price move, so bounded oscillators saturate at their edges. ⚠️ (v1 kpi L77) Take `is_limit_locked` from the feed's ceiling/floor fields (section 6).

## 2. Moving averages and the incremental EMA

⚠️ (v1 04 §2, L24)

```
SMA(n, t) = mean(close[t-n+1 .. t])
EMA(n, t) = alpha * close[t] + (1 - alpha) * EMA(n, t-1),   alpha = 2 / (n + 1)
slope(n, k)    = MA_n[t] / MA_n[t-k] - 1        (k = 5 or 20)
distance(n)    = close[t] / MA_n[t] - 1
```

- Horizons ⚠️ (v1 04 L37-40): MA20 ≈ one trading month (short trend) · MA50 ≈ one quarter · MA100 an intermediate filter · MA200 the long-term trend of one symbol.
- A trend label built from several MAs returns `unknown` while any input is still in warm-up; it never guesses. ⚠️ (v1 04 L47-48) Thresholds on `distance` (v1 used one for "over-extended") are ❓.

**Incremental update for the intraday hot path.** ⚠️ standard algebra; v1 never ran an intraday path.

```
state at the end of session t-1:  EMA(n, t-1), and for SMA the last n closes
provisional during session t:     EMA_live = EMA(n, t-1) + alpha * (last_price - EMA(n, t-1))
                                  SMA_live = SMA(n, t-1) + (last_price - close[t-n]) / n
at the close of session t:        replace last_price by the official close and persist the state
```

- Each tick costs O(1). Only the end-of-session value is persisted; provisional values are display-only and are never written as history.
- HNX fixes its close at the closing auction, but post-close matching (PLO) adds volume until 15:00, so volume-based state is final only after 15:00. ⚠️ ([market-microstructure.md §2](market-microstructure.md#2-trading-sessions))
- **Rescale carried state on an ex-rights date.** History is back-adjusted while the stream is raw. SMA and EMA are linear in price, so before the first tick of an ex-rights session multiply the carried price state by that event's `adj_factor` (section 6) and divide carried volume state by it. ⚠️ derived from the v1 adjustment definition (v1 01 §7, L242-248), not tested in v1.

**Warm-up.** An indicator over n sessions is NULL (`is_warmup = true`) until n non-stale sessions exist. ⚠️ v1 convention (v1 04 L47; v1 cfg) Recursive indicators also depend on how they are seeded:

- v1 seeded the EMA family with the first value; the TA-Lib library seeds with the SMA of the first n values. Both converge to the same limit. `measured on v1, 2026-08-13`, 4 large-cap symbols, tolerance rtol 1e-6: SMA20 and MFI14 agree as soon as the window is full; EMA12 agrees from session 70, RSI14 from 193, ATR14 from 239, MACD from 242. v1 skipped 300 sessions before comparing. (v1 cfg `doi_chung_talib`)
- Choose one seeding method, document it in the model, and test the formula against an independent implementation after the burn-in measured above. Changing the seeding changes every value silently, and no structural test notices. ✅ (v1 cfg)

## 3. Volume measures

⚠️ formulas (v1 04 §4, L134-145; v1 kpi L82). Inputs are `match_qty` and `match_value_vnd`; put-through creates fake volume spikes.

```
volume_ma20     = SMA(match_qty, 20)
volume_ratio    = match_qty / volume_ma20                      (v1 vol_ratio)
value_ma20_vnd  = SMA(match_value_vnd, 20)
turnover_ratio  = match_qty / free_float_shares
OBV[t]          = OBV[t-1] + sign(close[t] - close[t-1]) * match_qty
typical_price   = (high + low + close) / 3
money_flow      = typical_price * match_qty
MFI(14)         = 100 - 100 / (1 + positive_money_flow_14 / negative_money_flow_14)
VWAP            = sum(price * qty) / sum(qty)   over the session's matched trades
```

- **VWAP needs trade-level data**; v2 computes it from the stream, per session, from matched trades only. It is the reference for execution quality. ⚠️ (v1 04 L144; v1 kpi L82)
- `volume_ratio` intraday compares a partial session with full-session averages; any intraday use needs a time-of-day volume profile. ❓ never measured on v1.
- `turnover_ratio` needs point-in-time free-float shares ([data-quality-lessons.md §5](data-quality-lessons.md#5-share-counts-are-a-time-series-a-today-count-is-never-applied-to-the-past)). The free-float source is ❓.
- v1's reading zones for `volume_ratio` (dry-up, normal, surge, abnormal) are ❓ and carry no numbers here. A very large `volume_ratio` is first checked as a data event: a news item, an ex-rights date, put-through leaking into `match_qty`, or a bad row. ⚠️ (v1 04 L156)
- MFI equals exactly 0 over windows with no up session, and can come out as `-0.0`; compare it with an absolute tolerance, not a relative one. `measured on v1, 2026-08-13` (v1 cfg)

## 4. Liquidity: ADV20, point-in-time

- `adv_20d_vnd` = mean of `match_value_vnd` over the **20 previous sessions, excluding the current one** (`ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING`). It is the basis of `is_in_universe`; including the current session is look-ahead. ⚠️ (v1 05 §3, L201-204; v1 CLAUDE decision 3) Tests: [data-quality-lessons.md §3](data-quality-lessons.md#3-universe-membership-is-decided-from-the-past-and-delisted-symbols-stay-in-history).
- v1 computed the window over non-stale sessions only and marked a value `insufficient` when fewer than 15 sessions were in the window. ⚠️ v1 code (v1 05 §3). For an illiquid symbol, 20 traded sessions then span more than 20 market sessions. **Decided for P2 (ADR-0028):** v2 keeps v1's rule - the 20 previous non-stale rows, insufficient below 15 - in `dbt/dbt_project.yml` (`adv_window_rows`, `adv_min_rows`); stale sessions are skipped, not counted as zero.
- v1's liquidity tiers and position limits as a share of ADV are ❓ (never measured). **P2 keeps the tiers (100 / 30 / 10 bn VND) as provisional, unmeasured config** so the universe reproduces v1 for reconciliation (ADR-0028); they are not findings, and the research track measures them. An absolute VND floor drifts as the market grows; see [data-quality-lessons.md §23](data-quality-lessons.md#23-one-threshold-answers-one-question-and-ranking-happens-after-filtering).

## 5. Breadth and market-level measures

These come from price and volume alone, so they are the most reliable market-level measures. ⚠️ (v1 05 §6, L272-284) The breadth columns themselves (advancing, declining, `pct_advancing`) are defined in [flows.md §4](flows.md).

```
ceiling_floor_spread_ratio = (ceiling_count - floor_count) / active_symbol_count
pct_above_ma50             = count(close > MA50) / count(active, MA50 not in warm-up)
realized_vol_20d           = stdev(index_return, 20) * sqrt(250)
liquidity_momentum_ratio   = value_ma5 / value_ma60          (market matched value)
index_momentum_ratio       = index_close / index_MA125
foreign_net_ma20           = 20-session mean of market foreign net value (flows.md)
```

- **Express breadth as ratios to `active_symbol_count`, or as rolling z-scores, never as counts.** The active universe grew several-fold over v1's history, so a count threshold measures coverage, not behaviour: it is easy late in the series and impossible early on. ✅ `measured on v1, 2026-08-03 and 2026-08-05` (v1 03 §5 QT20, L330). Details and the calibration rule: [data-quality-lessons.md §22](data-quality-lessons.md#22-thresholds-on-a-growing-sample-are-ratios-and-changing-a-denominator-means-recalibrating).
- **Take `ceiling_count` and `floor_count` from the feed's `ceiling_price_vnd` / `floor_price_vnd`**, compared with raw prices. v1 estimated them from adjusted returns; those estimates are not inherited. ⚠️ (inventory A2; [data-quality-lessons.md §9](data-quality-lessons.md#9-raw-and-adjusted-prices-are-separate-columns-and-adjustment-is-only-trusted-when-it-can-be-checked-against-raw))
- The annualisation factor 250 is v1's convention for sessions per year. ⚠️ (v1 05 L281)
- Reading thresholds (for liquidity momentum, breadth zones, McClellan levels) and v1's composite fear/greed score with its weights are ❓ and are not carried over.

## 6. Back-adjustment and the tick grid

⚠️ formulas (v1 01 §7, L237-253). Event inputs: [market-microstructure.md §7](market-microstructure.md#7-ex-rights-adjustment).

```
adj_factor(e)      = reference_price_vnd(e) / close_before(e)       usually <= 1
cum_adj_factor(d)  = product of adj_factor(e) over every event e with ex_rights_date(e) > d
adjusted_price(d)  = raw_price(d) * cum_adj_factor(d)
adjusted_qty(d)    = raw_qty(d) / cum_adj_factor(d)                 traded value unchanged
```

- **Recompute `cum_adj_factor` over the full history every time a new event arrives**; never update it incrementally. The cost is negligible next to accumulated drift. ⚠️ (v1 01 L253)
- **Test the invariant** `adjusted_price × adjusted_qty ≈ raw_price × raw_qty` per row. The tolerance is ❓: v1 wrote one but never ran the test.
- **v1 never validated any adjustment.** It had no raw price, and corporate-action data covered 16 months against about 26 years of prices. ✅ `measured on v1, 2026-08-19` (v1 plan §2.24, L1790). v2's first raw prices come from the stream, from its start date; vendor history stays vendor-adjusted. See [data-quality-lessons.md §9](data-quality-lessons.md#9-raw-and-adjusted-prices-are-separate-columns-and-adjustment-is-only-trusted-when-it-can-be-checked-against-raw).
- **Adjusted prices sit off the tick grid by design**, because they are raw prices times a factor. Run the tick-grid test (`price % tick_size = 0`, tick from the `tick_size` seed by exchange, date and price) on `raw_price` only. ✅ `measured on v1, 2026-08-06`, full v1 adjusted close table: 0 of 4,516,729 rows off the 10-VND grid, and 1,301,977 of 2,538,188 rows (51.30%) off the full HOSE/HNX tick grid. (v1 plan §2.24, L1800-1825)
- Any price v2 derives for use as an order level is rounded onto the grid (section 7). ✅ (v1 plan L1812)

## 7. Rounding toward safety

**Incident.** A stop-loss candidate taken from a 26-session midpoint (Kijun) sat right next to the price in a narrow range. Rounding to the **nearest** tick lifted it exactly onto the entry price, so risk per share became 0 and position sizing divided by zero. ✅ `measured on v1, 2026-08-05`, 667 rows; the volatility of the affected rows was normal, so the cause was the rounding. (v1 07 §v2.0.5, L890-915)

What v2 does with any derived price level:

1. **Round in the direction that makes the computed risk larger.** For a long position: round the stop **down**, so the risk widens by at most one tick. ⚠️ (v1 07 L910-912) The same rule applied to an entry used only to compute risk rounds it up. ⚠️ derived, not tested in v1
2. **Bound it strictly.** A stop is at most the largest tick multiple **strictly below** the entry; without that bound a zero-width input still gives stop = entry. Record when the bound was applied. ⚠️ (v1 07 L913-914)
3. **Assign labels (which rule produced the value) on the unrounded value, before rounding.** Comparing a rounded value with unrounded candidates mislabelled most affected rows. ✅ `measured on v1, 2026-08-05` (v1 07 L915; v1 03 QT22, L332)
4. **Test every divisor for > 0** where it feeds sizing or a ratio, as its own dbt test. ⚠️ (v1 07 L904)
5. A level derived from adjusted prices is consistent with the model, not necessarily placeable on today's raw grid; state which grid it is on. ⚠️ (v1 07 L917-921)

## 8. Sources

**v1 KB (private):** `01_market_microstructure.md` §7 · `03_data_architecture_etl.md` §5 (QT20, QT22) · `04_technical_analysis.md` header, §2, §4, §11 · `05_flow_sentiment.md` §3, §6 · `07_decision_engine.md` §v2.0.5 · `_tham_khao/2026-08-16_kpi_chart_phan_tich_CK_VN.md` Layer 2 · v1 master plan §2.24 · v1 indicator config (TA-Lib cross-check) · v1 `CLAUDE.md` §4.
