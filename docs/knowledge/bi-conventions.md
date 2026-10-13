# BI conventions - Power BI on the dbt marts

Status: K0.3 translation of v1 KB rows labelled for this file in v1's knowledge inventory · Written 2026-10-13 · BI tool: Power BI Desktop, manual refresh (ADR-0010), reading `marts_*` only (spec S3).

**Evidence tags.** ✅ verified · ⚠️ design guidance or secondary source · ❓ unverified · `measured on v1, <date>`. **v1 never built a Power BI report and never ran a DAX measure.** Its DAX, model design and performance targets are written-down intent: every DAX item below is ❓ until it runs in v2. v1's measured facts come from its own HTML dashboard and colour validator; they carry over as rules, not as numbers about v2. **Source refs.** `(v1 08 §2.2, L74)` = v1 KB file `08_bi_semantic_dashboard.md`, section, line. Other v1 files: `00` index and conventions, `10` roadmap, `kpi` = `_tham_khao/2026-08-16_kpi_chart_phan_tich_CK_VN.md`.

**Conventions.** Dates ISO `YYYY-MM-DD`; timestamps stored UTC (`_at`), shown UTC+7. Prices integer VND. Ratios stored as decimals (`0.07`), formatted as % only in the report. Exchange strings `HOSE` | `HNX` (never `HSX`). Column and table names English `snake_case`; Vietnamese only in display labels. ⚠️ (v1 00 conventions, L42) Suffixes follow spec §13.2.

---

## 1. Model

- **Use a star with one wide daily fact per grain.** VertiPaq compresses a wide table well; v1 planned ~60 columns × ~8.5 M rows in one `fct_daily`. A table with an extra grain (for example a per-horizon signal table) is a separate fact. ⚠️ ❓ never loaded in Power BI (v1 08 §1, L34)
- **Relate facts only through dimensions, single-direction, one-to-many.** Bi-directional filters are ambiguous and slow; when a measure needs a reverse filter, use `TREATAS` or `CROSSFILTER` inside that measure. Replace many-to-many with a one-to-many bridge. ⚠️ (v1 08 §1, L41; v1 08 §7, L428)
- **Never relate a fact to a fact at a finer grain.** v1's LookML join of `fct_signal` (symbol × date × 3 horizons) to `fct_daily` multiplied every summed measure by 3 the moment a signal field was used. The Power BI equivalent is a relationship to a table with a hidden extra key: sums inflate silently. Filter the extra key to one value, or keep the tables apart. ⚠️ lesson from LookML; Power BI form ❓ (v1 08 §3, L258)
- **Import the trading calendar as the date table.** v2's dbt model is `dim_trading_calendar` (v1 called it `dim_date`). It is a trading calendar, not a civil one ⚠️ (v1 08 §1, L39, L43; v1 kpi semantic model, L166):

| Column | Meaning |
|---|---|
| `trade_date` | key |
| `session_seq` | gap-free integer over trading days; the key of all time intelligence |
| `is_trading_day` | from the holiday seed plus observed sessions |
| `year`, `quarter`, `month`, `week_of_year` | civil parts |
| `trading_week_id`, `trading_month_id`, `fiscal_quarter_label` (`2026Q3`), `trading_year_id` | period keys built from trading days |
| `session_count` per period | sessions in that week / month / quarter / year |
| `is_month_end_session`, `is_quarter_end_session` | last **trading** session of the period, not the last calendar day |
| `holiday_name`, `days_to_next_holiday` | liquidity thins before long holidays |
| `is_ex_rights_date` (per symbol, in the fact), special-session flags | VN calendar events |

- **Recompute every period key when the session set changes.** Period keys are functions of the session set. v1 fixed its calendar, renumbered sessions and left 21 sessions with a NULL `trading_week_id`, which became a phantom week bucket. `measured on v1, 2026-08-06` (v1 08 §v2.7.2 A, L453; v1 10 L622) See [data-quality-lessons §36](data-quality-lessons.md).
- **Treat `session_seq` as a stable key.** Stored rows may reference it (v1's order ledger stored an expiry `session_seq`). Before rewriting the calendar, compare old and new `session_seq` and write only on 0 differences. ✅ v1 measured 0 / 5,766 before writing (v1 08 §v2.7.2 A, L479)
- **The price fact holds raw and adjusted prices side by side, plus the feed's `reference_price_vnd`, `ceiling_price_vnd` and `floor_price_vnd`.** ⚠️ (v1 kpi semantic model, L166) Disclosed figures join on `available_from_date`, never on the period end. ⚠️ (v1 kpi L166) See [data-quality-lessons §4](data-quality-lessons.md).
- **Performance.** ⚠️ ❓ never measured on Power BI (v1 08 §7, L422):
  - Import **the last 3 years** of daily facts; query longer history from BigQuery when needed.
  - Pre-compute every non-trivial measure in the gold marts; DAX does `SUM` / `AVERAGE` / counts.
  - Keep long text columns (evidence notes, risk text) out of the main fact; put them in a side table used only by drill-through.
  - Incremental refresh by `trade_date` does **not** apply: Desktop with manual refresh reloads the whole import. Keep the import small instead.
  - v1's target "every page renders in < 3 s" is a target, not a measurement. ❓

## 2. DAX

All items ❓: written in v1, never run.

- **Do time intelligence by session, never by civil date.** `DATEADD`, `SAMEPERIODLASTYEAR` and `PREVIOUSDAY` walk the civil calendar and land on weekends and holidays (BLANK or wrong). Index on `session_seq` instead. ❓ (v1 08 §2.2, L74)

```dax
Close N Sessions Ago =
VAR CurSeq = SELECTEDVALUE ( dim_trading_calendar[session_seq] )
VAR N = [Param N Sessions]            -- what-if parameter
RETURN
    CALCULATE (
        SELECTEDVALUE ( fct_price_daily[close_adjusted_vnd] ),
        FILTER ( ALL ( dim_trading_calendar ), dim_trading_calendar[session_seq] = CurSeq - N )
    )
```

  The same pattern gives an N-session return, a moving average (`session_seq > CurSeq - N && session_seq <= CurSeq`) and YTD from the year's first `session_seq` with `is_trading_day = TRUE()`. ❓ (v1 08 §2.2, L78-L114)
- **Wrap column-vs-column comparisons in `FILTER`.** A boolean filter argument of `CALCULATE` may reference only one column; `close > ma50` needs `FILTER(fct, fct[close] > fct[ma50])`. ❓ (v1 08 §2.3, L133)
- **Exclude stale sessions in every measure** (`is_stale = FALSE()`), and warm-up rows for indicator-based measures. A stale session has zero volume and a copied price. ⚠️ (v1 08 §2.3, L117; CONTEXT `is_stale`)
- **Count ceiling and floor from the feed's fields**, never from adjusted prices: ceiling count = sessions with the raw close equal to `ceiling_price_vnd`. v1's version compared `close_raw`, which was 100% NULL, so its counts never worked. ✅ v1 limitation (v1 08 §2.3, L135; inventory A2)
- **Breadth measures** count distinct symbols: % above MA50, advance/decline ratio, top-10 turnover concentration (`TOPN(10, ...)` over turnover ÷ all symbols). ❓ (v1 08 §2.3, L119-L146) Advancing share excludes unchanged symbols; definitions live in `flows.md`.
- **Put complex logic in dbt.** Streaks, state machines, divergence and anything sequential is a gold column; DAX only aggregates and filters. v1 names this the first cause of slow Power BI reports. ⚠️ (v1 08 §2.4, L167; v1 08 §7, L427) A measure that reads a pre-computed column is `SELECTEDVALUE(fct[foreign_streak])`.

## 3. Aggregation over periods

- **One aggregation rule per metric, and the column name states it.** ✅ v1 built and used this (v1 08 §v2.7.2 B, L483):

| Metric family | Rule | Suffix (v2) |
|---|---|---|
| Flows: turnover, net foreign value | sum | `_sum` |
| Ratios, scores | mean | `_avg` |
| Index level | last value in the period (`arg_max` by `session_seq`) | `_close` |
| Sessions with property X | count, and share of sessions | `_count`, `_ratio` |

- **A period column never reuses the daily column's name.** `pct_above_ma200` is one session; its monthly mean is `pct_above_ma200_avg`. Equal names invite the wrong aggregation. ⚠️ (v1 08 §v2.7.2 B, L492)
- **`session_count` is mandatory on every period row.** A month holds 14 to 23 sessions (64% spread), so counts and sums of two months are not comparable without it. `measured on v1, 2026-08-06, v1 trading calendar` (v1 08 §v2.7.2 B, L497)
- **Flag open periods** with `is_period_complete`. ⚠️ (v1 08 §v2.7.2 B, L500)
- **Gate period aggregates on session coverage, separately from symbol coverage.** A closed period with missing sessions for a dataset shows blank (⚪), not 0: a 0 net foreign flow reads "balanced", which is false. The open period is exempt, because a source one session behind is normal. ✅ v1 gate with planted faults (v1 08 §v2.7.2 B, L502; v1 10 L622) See [data-quality-lessons §13, §14, §17](data-quality-lessons.md).
- **Set implicit aggregation off** on numeric columns (summarize by: none) so every visual uses an explicit measure. ❓ v2 practice, not in v1

## 4. Colour

v2 does not inherit v1's colour values. The palette is designed and measured separately; this section carries the rules and the measurement method.

**The v2 palette** lives in [`config/palette.yml`](../../config/palette.yml) (ADR-0026), one block per theme, values chosen in OKLCH. `tools/check_palette.py` measures it against the rules below and CI runs it; the research behind the thresholds is [`../design/colour-and-ux-research.md`](../design/colour-and-ux-research.md). ✅ measured 2026-10-13, 22 of 22 rules on both themes.

| Role | Light | Dark | Use |
|---|---|---|---|
| `up` · `down` | `#067F5C` · `#B00326` | `#40CD9B` · `#EF675C` | Price up / down, as text and marks |
| `ceiling` · `floor` · `reference` | `#8E47CD` · `#017A9B` · `#9D6304` | `#A36FD9` · `#5EC6EC` · `#E0AE57` | Price-board states |
| `up_weak` · `up_strong` | `#BBF2E2` · `#067F5C` | `#003F33` · `#016246` | Heat scale, positive side |
| `down_weak` · `down_strong` | `#FFCEBD` · `#B00326` | `#4A2010` · `#8C2D28` | Heat scale, negative side |
| `neutral` | `#E9EBEE` | `#232426` | Heat-scale midpoint, unsigned cells |
| `cat_1` .. `cat_5` | blue, orange, magenta, olive, slate | lighter versions | Series identity only, never price meaning |

The config is the source; this table is a reading aid. Measured pairs that matter most: up vs down CIEDE2000 under deuteranopia 18.5 (light) and 14.4 (dark), protanopia 13.0 and 19.3; every price-role colour is readable as text at 4.5:1 or more on both backgrounds and surfaces.

- **Follow the VN price-board semantics.** Up = green · down = red · ceiling = purple · floor = cyan · reference / unchanged = yellow-amber. Wrong colours are misread instantly; this is a convention, not a taste. ⚠️ (v1 08 §6, L388; v1 10 L152)
- **Keep score and status colours apart from price colours.** ⚠️ (v1 08 §6, L402)
- **Colour carries a verdict, not a sign.** Do not reuse up/down hues for non-price signs (a negative correlation is not "bad"). Show the sign by direction and an explicit ±. The position in a 52-week range uses a neutral colour: the top of the range is not good or bad by itself. ⚠️ (v1 08 §v2.9.30 G, L790)
- **At most 5 categorical colours.** v1 found no combination of 6 or more that passed its colour-vision check. `measured on v1 palette, 2026-08-06` (v1 08 §v2.7.2 C, L521)
- **Green vs red needs CVD distance ΔE ≥ 8** (simulated colour-vision deficiency). ΔE 6-8 is a floor, valid **only** with secondary encodings; normal-vision ΔE has a floor of 15. v1's light pastel pair failed hard (CVD 3.4, normal 11.1) while its strong pair passed (8.5). ✅ `measured on v1 palette, 2026-08-17` (v1 08 §v2.7.2 C, L535; v1 10 L622)
- **Measure every background separately.** The same pairs measured differently on v1's dark theme (2026-08-23). A number quoted for a pair belongs to that pair and that background; v1 once quoted the number of a rejected candidate as the running scale's. ✅ (v1 08 §v2.7.2 C, L550)
- **Diverging heat scales use exactly two steps per hue.** A third step failed both in-cell text contrast and step separation on v1. Hue carries the sign, lightness the magnitude. ✅ `measured on v1 palette, 2026-08-17` (v1 08 §v2.7.2 C, L570)
- **Three secondary encodings are mandatory on every green/red heat cell:** ▲▼ glyph · signed number in the cell · edge mark (top for up, bottom for down). They are conditions of the rule, kept even where ΔE passes. A cell too small for a number is grey, not signed. Polar bars (net foreign flow) carry an explicit ± and their position against the zero line. ✅ (v1 08 §v2.7.2 C, L566-L581)
- **The midpoint of a diverging scale is neutral**, never yellow or orange. ✅ (v1 08 §v2.7.2 C, L573; v1 10 L622)
- **Measure text inside cells separately from the scale.** A scale can pass step separation and still fail text at 4.5:1. Body text ≥ 4.5:1 on its actual background. ✅ (v1 08 §v2.7.2 C, L531)

## 5. Visual rules

- **One block answers one question; the chart type follows the question.** Fix monotony by adding questions, not by drawing the same answer three ways. ⚠️ (v1 08 §v2.9.30 A, L713)
- **Put the message at the top of the page.** Time series run horizontally, structure comparisons vertically; scale consistently; maximise data-ink. ⚠️ IBCS / Tufte / Few (v1 kpi §B, L33); v1 notes IBCS became ISO 24896:2026 ❓
- **Bars and columns start at 0.** ⚠️ (v1 kpi §B, L33; v1 kpi anti-patterns, L155)
- **Use bullet charts instead of gauges and sparklines for trends in tiles.** No pie, donut, 3D, gauge, arbitrary dual axis, stacked area with many series (use small multiples) or candlesticks for non-OHLC data. This list wins over v1's dashboard drafts, which still had a gauge and a donut. ⚠️ (v1 kpi L155; v1 08 §4, L287, L334)
- **Small multiples share one scale**, computed over all panels; each panel keeps its own baseline when the objects differ. ⚠️ (v1 08 §v2.9.30 E, L769)
- **All cells about one quantity use the same unit and scale.** v1 printed a 12-digit change next to "517.5 bn USD". ✅ v1 incident (v1 08 §v2.9.31 F, L872)
- **Formats.** Prices integer VND, no decimals. Turnover in billion VND (tỷ) with thousands separators. Ratios with 1 decimal and %. ⚠️ (v1 08 §6, L412)
- **Time axes are categorical by session**, so weekends and holidays leave no gaps. ⚠️ (v1 08 §6, L416) One chart holds one frequency: a monthly line next to a daily line looks flat between releases. ✅ (v1 08 §v2.9.33, L993)
- **Every page shows `as_of` and the data-quality state.** ⚠️ (v1 08 §6, L418; v1 10 L152)
- **A visual takes all its axes from one `as_of`.** v1 drew x from the latest session and y from a field published one session later: every point was NULL and the frame was empty. ✅ incident 2026-08-06 (v1 08 §v2.7.2 D, L583)
- **An empty visual says why and how many are missing**, per column. An empty frame otherwise states "nothing qualifies", a claim about the market, when the truth is "no data yet". ✅ (v1 08 §v2.7.2 D, L592)
- **Put each warning next to the thing it describes**, not in a page-wide banner. When removing UI, list every message it carried and verify each one has a new place. v1 found a lost message only because a check enforced it. ✅ (v1 08 §v2.9.32 B-C, L910)
- **Recorded numbers carry their measurement date and n**, and point to where the live number is. ⚠️ (v1 08 §v2.9.30 H, L801)
- **No emoji as marks or labels in visuals.** They ignore the theme colour and their contrast cannot be measured; use text. ⚠️ (v1 08 §v2.9.30 F, L784)
- **Setup list (hot path).** Per symbol: price, supports, stop, target, R:R, with a level ladder where shape is the secondary channel (support vs resistance vs stop vs price). Show levels only when their session equals the list's session. ⚠️ (v1 08 §v2.9.33, L995)
- **Dark theme, if shipped, is verified page by page.** v1's check that inspected only the visible tab missed every planted fault on the other tabs. A theme without dark tokens gets no dark switch. ✅ (v1 08 §v2.9.23 E, L670)
- **Market overview page** (hot path, spec §4), top to bottom ⚠️ (v1 08 §4 DB-01, L283; v1 kpi layout, L166):

| Area | Content | Visual |
|---|---|---|
| Header | session date, `as_of`, data-quality state | text |
| KPI row | VN-Index (points, %) · HNX-Index · market turnover (tỷ) · net foreign (tỷ) | 4 tiles with sparklines |
| Breadth | advancing / declining / ceiling / floor counts, % above MA50 / MA200 | tiles + session sparkline |
| Main chart | VN-Index and % above MA200, two panels on one session axis | small multiples, not dual axis |
| Sectors | ICB level 2 returns 1D / 5D / 20D, size = market cap | treemap with the two-step scale |
| Foreign flow | daily net (polar bars) and cumulative, two panels | bars + line |
| Tables | top 10 gainers / losers · top 10 turnover · top 10 foreign buy / sell | 3 small tables |

  No regime badge and no Fear/Greed gauge: both are outside v2's scope.

## 6. Acceptance checklist

Each item is checked by a tool, not by eye. Measures and pages can only be checked from a text export of the report (PBIP / TMDL), which is open. ❓ (v1 08 §8, L436; v1 10 L152)

- [ ] `dim_trading_calendar.session_seq` matches the dbt calendar 100% (dbt test plus a query from the model).
- [ ] No measure contains `DATEADD`, `SAMEPERIODLASTYEAR` or `PREVIOUSDAY` (scan of the measure text).
- [ ] No measure implements streaks or state machines (they are dbt columns).
- [ ] No bi-directional relationship; every relationship is one-to-many from a dimension.
- [ ] Every period table has `session_count` and `is_period_complete`.
- [ ] The theme palette passes the palette check: price-board roles, ≤ 5 categorical colours, green/red CVD ΔE, two steps, neutral midpoint, text 4.5:1, on each background shipped.
- [ ] Every page has an `as_of` and a data-quality visual.
- [ ] No pie, donut, gauge or 3D visual type in the report.

## 7. Open questions (❓)

| # | Question | Effect |
|---|---|---|
| 1 | Import or DirectQuery for hot-path views under manual refresh? | Refresh time, BigQuery cost |
| 2 | Is the report saved as PBIP/TMDL so measures can be checked by a tool? | §6 checklist |
| 3 | Does any v1 DAX pattern behave differently on BigQuery-imported types? | §2 |
| 4 | Intraday time axis: categorical by time of day, skipping the 11:30-13:00 lunch break? | Hot-path charts |

## 8. Sources

**v1 KB (private):** `08_bi_semantic_dashboard.md` §1-§4, §6-§8, §v2.7.2 A-D, §v2.9.23 E, §v2.9.30 A, E-H, §v2.9.31 F, §v2.9.32 B-C, §v2.9.33 · `00_INDEX.md` conventions · `10_roadmap_backlog.md` GĐ3, 2026-08-06 entry with the 2026-08-17 correction · `_tham_khao/2026-08-16_kpi_chart_phan_tich_CK_VN.md` §B, anti-patterns, semantic model.

New terms used here are defined in [`../../CONTEXT.md`](../../CONTEXT.md).
