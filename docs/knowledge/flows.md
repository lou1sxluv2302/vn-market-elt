# Flows and breadth - foreign, proprietary, market breadth, index contribution

Status: K0.3 translation of v1 KB rows labelled for this file in v1's knowledge inventory · Written 2026-10-13 · v1 facts as of 2026-08.

**Evidence tags.** ✅ verified · ⚠️ documentation, news or a v1 design note (secondary unless a primary source is linked) · ❓ unverified or never measured · `measured on v1, <date>` = measured on v1's own warehouse, which was rebuilt twice, so its numbers are orders of magnitude; the population is given with each one. **Source refs.** `(v1 05 §1, L17)` = v1 KB file `05_flow_sentiment.md`, section, line. Other v1 files: `02` data sources, `04` technical analysis, `08` BI dashboard, `10` roadmap, `kpi` = `_tham_khao/2026-08-16_kpi_chart_phan_tich_CK_VN.md`.

**Conventions.** Values are VND (`_vnd`), quantities are shares (`_qty`). Rolling windows count sessions by `session_seq`, never calendar days. "Matched" is `match`, "put-through" is `put_through`, as in [`../../CONTEXT.md`](../../CONTEXT.md). Which source supplies each flow, its history and its traps are in [`data-sources.md`](data-sources.md) §4; this file defines the measures built on top.

**Thresholds.** v1 printed interpretation zones (pressure "strong", breadth "hot", McClellan readings) that it never measured. They are recorded here as ❓ with no number. Calibrate them on v2 data before any of them is displayed as a rule.

---

## 1. Why flows matter

- **Foreign flow is watched far beyond its share of trading.** Its share of traded value is ❓: v1 gave a figure without a source, so none is carried here. (v1 05 §1, L10)
- **Foreign flow tends to persist**: a net-buying run often lasts weeks. ⚠️ v1 claim, not measured in v1. (v1 05 §1, L14)
- **2025 was a record net-selling year**: 134,788 bn VND (about 5.1 bn USD), 2.92 bn shares across the three exchanges; HOSE alone about 125,000-129,000 bn VND. ⚠️ press figure, dated 2026-08-16. (v1 kpi L107)
- **Market-level events move foreign flow mechanically** ⚠️: the FTSE upgrade (effective 2026-09-21) and index reviews. Dates and status are in [`market-microstructure.md`](market-microstructure.md) §9 and §11; treat them as event annotations (section 2.3).
- **VN-Index is uncapped**, so a few large caps can lift it while most stocks fall. Breadth (section 4) and index contribution (section 5) exist to expose that. ⚠️ (v1 04 §7, L268; [`market-microstructure.md`](market-microstructure.md) §9)
- Index composition, foreign ownership limits, Decree 245/2025 and bank room are in [`market-microstructure.md`](market-microstructure.md) §9-§10; they are not repeated here.

## 2. Foreign flow

### 2.1 Measures

Per symbol and session. Build every measure on the **matched** part; put-through is kept as its own column. ⚠️ v1 design (v1 05 §1, L17; v1 02 §v1.4, L535)

| Measure | Definition |
|---|---|
| `foreign_net_match_value_vnd` | foreign matched buy value - foreign matched sell value |
| `foreign_net_put_through_value_vnd` | the same on put-through trades; never mixed into the matched measures |
| `foreign_net_ma5` / `foreign_net_ma20` | simple mean of the matched net over the last 5 / 20 sessions |
| `foreign_net_cum20` | sum of the matched net over the last 20 sessions |
| `foreign_intensity` | (foreign matched buy + foreign matched sell) / `match_value_vnd` - participation share |
| `foreign_pressure` | `foreign_net_match_value_vnd / NULLIF(match_value_vnd, 0)` - the main foreign measure |
| `foreign_streak` | consecutive sessions with the same sign of the matched net |
| `foreign_own_pct` | (`shares_outstanding` × `foreign_ownership_limit_ratio` - end-of-day `foreign_room_remaining_qty`) / `shares_outstanding` |
| `room_used_pct` | `foreign_own_pct / foreign_ownership_limit_ratio` |

- Numerator and denominator of every ratio use the **same trade type**. v1's `foreign_intensity` divided buy + sell of unstated type by matched value; use matched over matched. ⚠️ (v1 05 §1, L22)
- `foreign_own_pct` needs **point-in-time** shares (`is_shares_pit`). The source's room columns give three independent daily share estimates; the acceptance rule is in [`data-sources.md`](data-sources.md) §4. ✅ (v1 02 §v1.4, L539)
- A full room (`room_used_pct` near 1) means foreigners cannot buy more, which removes one source of demand. The cut-off is ❓. (v1 05 §1, L58)
- How a zero net or a NULL breakdown affects `foreign_streak` (reset, carry, NULL) is ❓; decide it in the model and test it on known answers.

### 2.2 Data traps

1. **Room is deducted at order entry since KRX (2025-05-05)**, not at matching. Intraday `foreign_room_remaining_qty` is not ownership; use the **end-of-day snapshot** for `foreign_own_pct` and `room_used_pct`. ⚠️ re-verify (v1 05 §1, L33; [`market-microstructure.md`](market-microstructure.md) §10)
2. **Put-through distorts foreign flow.** One 500 bn VND negotiated deal can show as a "record net buy" with no effect on the order book. Split matched from put-through at load and use matched for every measure. ⚠️ (v1 05 §1, L35)
3. **ETF and index-rebalance flow is mechanical**, not a view. Flag review days of the indices (January and July for the VNAllshare family) and effective dates of index-provider events, and keep a column that lets consumers exclude them (section 6). ⚠️ (v1 05 §1, L38)

### 2.3 Matched + put-through must equal total - test it per row

- The source encodes "unknown" as **0** in the matched and put-through columns, not NULL. A 0 is also a valid value (no put-through that day), so no single column can tell "no trading" from "no data"; only the identity `match + put_through = total` exposes it. ✅ (v1 10 §1.27, L99)
- In v1, 110 of 111 failing rows had matched = 0 and put-through = 0 while total > 0. Read as data, that says "foreigners did nothing" on a day they traded 87 bn VND - a wrong-sign error, worse than a gap. `measured on v1, 2026-08-03`, 5 symbols (v1 10 §1.27, L99)
- On the prop source the same identity NULLed 6,578 of 145,272 rows (4.53%); the rest were clean. `measured on v1, 2026-08-04` (v1 05 §2, L174)
- Foreign matched/put-through splits were reliable only **from 2020**; earlier rows carried 0 instead of NULL. `measured on v1, 2026-08` (v1 DQ test 16 note)
- **In v2** (`fct_foreign_flow_daily`, `fct_prop_flow_daily`, tolerance 0): foreign from 2020, 2,446,939 rows keep the split and 9,227 lose it - 4,678 v1 had already NULLed and 4,549 that v1's own flag passed although match + put-through missed total by more than 1,000; all 1,324,041 earlier rows lose it by the 2020 rule. Prop: 142,665 keep it, 6,716 lose it (176 of them passed v1's flag). Rounding the source's doubles to integers never opened a gap of 1-2. ✅ `measured on v2 prod, 2026-10-16`
- **What to do:** test the identity on every row and every side (buy, sell; quantity, value). When it fails beyond a tolerance, set the matched and put-through columns to NULL, keep total, and set `is_breakdown_valid = false`. Never overwrite total.
- **Never mix definition types in one series.** v1's foreign table held total-based rows; appending matched-based rows would have produced one column with two meanings and no failing test. The fix was a full reload. Keep one definition per column, carried by the `match_` / `put_through_` / `total_` prefix, and reload rather than append when a definition changes. ✅ (v1 10 §1.24, L95; v1 10 §1.36, L102)
- Price `volume` is matched only; a source's total volume adds put-through. The gap is by definition, so never test them for equality. See [`data-quality-lessons.md`](data-quality-lessons.md) #35 and [`data-sources.md`](data-sources.md) §4.

## 3. Proprietary flow

### 3.1 Measures

⚠️ v1 design (v1 05 §2, L185)

| Measure | Definition |
|---|---|
| `prop_net_value_vnd` | prop buy value - prop sell value (matched part when the source splits it ❓) |
| `prop_net_ma10` | simple mean of `prop_net_value_vnd` over the last 10 sessions |
| `prop_pressure` | `prop_net_value_vnd / NULLIF(match_value_vnd, 0)` |
| `prop_data_available` | whether a prop value exists for this symbol and session |

### 3.2 Interpretation: warrant hedging

- Securities firms trade for their own book **and** to delta-hedge covered warrants they issued. When a firm has warrants outstanding on symbol X, it must buy X to hedge, so net prop buying can be purely technical. ⚠️ (v1 05 §2, L192)
- **What to do:** show prop flow with an annotation of outstanding `covered_warrant` issues on the symbol. Without that information, label the prop reading low confidence. ⚠️ (v1 05 §2, L195)

### 3.3 Data gaps

- HOSE stopped publishing prop data in early March 2022; public sources now fold it into `domestic_institution`. ⚠️ (v1 05 §2, L178; v1 02 §v1.5, L580) v1's prose gives 2022-03-01 while the gap measured below starts on 2022-03-03; the exact date is ❓.
- History starts in **2020**, with a gap of exactly 50 sessions (2022-03-03 → 04-29 and 2022-05-04 → 05-16). Coverage falls steeply with liquidity. ✅ `measured on v1, 2026-08-04`, 145,293 rows (v1 02 §v1.5, L586). Detail: [`data-sources.md`](data-sources.md) §4.
- **What to do:** model `prop_` as nullable and **best-effort**; it can stop at any time. Nothing downstream may require it. Carry `prop_data_available`, use 0 only where the symbol is eligible point-in-time ([`data-sources.md`](data-sources.md) §4), and cross-check prop totals against `domestic_institution` where both exist. ⚠️ (v1 02 §v1.5, L607)

## 4. Breadth columns

Grain: `exchange × trade_date`. Count only non-stale sessions (`is_stale = false`). ⚠️ (v1 04 §7, L253)

| Column | Definition |
|---|---|
| `advancing_count` / `declining_count` / `unchanged_count` | symbols closing above / below / at the reference price |
| `pct_advancing` | `advancing / (advancing + declining)` - **unchanged excluded** |
| `ad_ratio` | `advancing / declining` |
| `ad_line` | running sum of `advancing - declining` |
| `pct_above_ma50` / `pct_above_ma200` | symbols with close > MA, over `active_symbol_count` |
| `ceiling_count` / `floor_count` | from the feed's ceiling/floor fields, never from adjusted prices |
| `new_high_52w_count` / `new_low_52w_count` | symbols at a 52-week high / low |
| `mcclellan_osc` | `EMA19(A - D) - EMA39(A - D)`; EMA as in [`indicators.md`](indicators.md) |
| `top10_value_share` | traded value of the top 10 symbols / traded value of the exchange |

- **`pct_advancing` excludes unchanged symbols.** Unchanged symbols in the denominator pull the mean below the neutral 0.5 the ratio is read against. v1's size of that pull is not carried over (population never stated); re-measure it on v2 data ❓. (v1 04 §7.5b, L401)
- **Ceiling and floor counts come from the feed's fields**: rule and reason in [`indicators.md`](indicators.md) §5.
- **Value concentration is not index-point concentration.** A single large cap can carry about 40% of a session's index move with about 5% of its traded value ⚠️. Keep `top10_value_share` as a liquidity measure only. (v1 04 §7.8b, L436)
- **Thresholds ❓**: A/D ratio zones, "% above MA" hot/oversold and bull/bear lines, ceiling/floor "panic" counts, top-10 share risk level, McClellan readings. v1 printed numbers for all of them, unmeasured. (v1 04 §7, L255)

## 5. Index contribution

Per symbol and session: `contribution = (close - reference) × shares_outstanding`. The index divisor is constant within a session, so it **cancels** in every share; neither the divisor nor the index point change is needed, and no denominator goes to zero on a flat day. ✅ (v1 04 §7.2b, L298)

| Column | Definition |
|---|---|
| `top3_index_contribution` | Σ\|contribution\| of the top 3 / Σ\|contribution\| of all HOSE symbols |
| `top3_cap_share` | market cap of those same 3 / HOSE market cap |
| `concentration_ratio` | `top3_index_contribution / top3_cap_share` |
| `top3_contrib_z250` | (top3 - mean of the previous 250 sessions) / std of the previous 250 sessions |
| `top1_direction` | sign of the leading symbol's contribution |

- **Use a relative measure, not the raw share.** The raw top-3 share rises as fewer symbols trade, so an absolute threshold measures data coverage, not market behaviour; `concentration_ratio` and the z-score are the candidates that should not. v1's correlations are not carried over; re-measure them on v2 data ❓ (lesson: [`data-quality-lessons.md`](data-quality-lessons.md)). (v1 04 §7.1b, L281; §7.2b, L298)
- **The z-score window is `ROWS BETWEEN 250 PRECEDING AND 1 PRECEDING`**, excluding the current session. Including it pulls the mean and deviation towards the value being scored (z shrinks) and is look-ahead. Require a minimum history, else NULL; v1 used 200 sessions, a data-sufficiency guard never calibrated (❓, set it in config). ✅ window rule (v1 04 §7.2b, L311; §7.7b, L426)
- **HOSE only**: VN-Index contains only HOSE stocks. From 2026-12-28 former HNX stocks trade on HOSE; whether VN-Index absorbs them is ❓ ([`market-microstructure.md`](market-microstructure.md) §13 #10). ⚠️ (v1 04 §7.7b, L426)
- **Denominator: every HOSE symbol with a price**, not the liquid universe; a universe denominator inflates the top-3 share. ⚠️ (v1 04 §7.7b, L426)
- **Point-in-time shares are required** (`is_shares_pit = true`); today's share count applied to the past is look-ahead. ⚠️ (v1 04 §7.7b, L426)
- **Require a minimum number of symbols** in the session; below it the top 3 dominate trivially. v1 used 50, never calibrated (❓, set it in config). ⚠️ (v1 04 §7.7b, L426)
- Columns that cannot be evaluated (too few symbols, short history, no PIT shares) are **NULL**, not false or 0. ⚠️ (v1 04 §7.6b, L416)
- v1 used adjusted close and previous close. In v2 use raw close and the feed's `reference_price_vnd`, which carries ex-rights adjustment on the ex-date. ❓ v2 design; VN-Index weighting (free float or not) is open ([`market-microstructure.md`](market-microstructure.md) §13 #1).

## 6. Candidate columns for `fct_flow_daily` and chart notes

### 6.1 Candidate columns ❓ (design, not built)

Grain `symbol × trade_date`. Derived from v1's specification, restricted to flows. (v1 05 §9, L479)

| Group | Columns |
|---|---|
| Key | `symbol`, `security_id`, `trade_date` |
| Foreign | `foreign_buy_match_value_vnd`, `foreign_sell_match_value_vnd`, `foreign_net_match_value_vnd`, `foreign_net_put_through_value_vnd`, `foreign_net_ma5`, `foreign_net_ma20`, `foreign_net_cum20`, `foreign_intensity`, `foreign_pressure`, `foreign_streak`, `is_breakdown_valid` |
| Room (end of day) | `foreign_room_remaining_qty`, `foreign_own_pct`, `room_used_pct` |
| Prop (nullable) | `prop_net_value_vnd`, `prop_net_ma10`, `prop_pressure`, `prop_data_available` |
| Liquidity | `match_value_vnd`, `adv_20d_vnd` |
| Events | `is_index_event_day` (index review or index-provider effective date) |

- Margin, insider, sentiment and composite scores from v1's table belong to other models; v1's flow-by-price regime matrix is research and is not carried over.
- Streaks and rolling windows are dbt columns, not BI measures: [`bi-conventions.md`](bi-conventions.md) §2.

### 6.2 Chart notes

- **Foreign and prop net flow: diverging bar** (sign and size), by day over 60 sessions, with the cumulative net as a line; by sector or market cap as a treemap. ⚠️ (v1 kpi L107; v1 08 §4, L292)
- **Foreign net MA20 and pressure in BI**: the window steps over `session_seq` (`seq > current - 20 AND seq <= current`), and pressure divides net matched by **matched** turnover. ⚠️ (v1 08 §2.4, L149)
- **VN-Index candles above a `pct_above_ma200` panel, sharing the session axis** (two panels, not a dual axis; [`bi-conventions.md`](bi-conventions.md) §5): v1's main divergence chart (index at a new high while the share above MA200 falls). The reading is ❓ - never measured; show it as context, not as a signal. (v1 08 §4, L296)
- Breadth charts: A/D line as a cumulative line, A/D ratio as line or bar, "% above MA" as a line with a 50% reference, McClellan as an oscillator around 0, new highs vs new lows as lines. ⚠️ (v1 kpi L102)
- Derivatives (basis, open interest) and ETF creation/redemption flows are out of scope for v2. ⚠️ (v1 kpi L111-113)

New terms used here are defined in [`../../CONTEXT.md`](../../CONTEXT.md).
