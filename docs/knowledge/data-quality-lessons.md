# Data-quality lessons inherited from v1

This file lists the data-quality and measurement lessons that v1 (the private research repo) learned from real incidents. Each one is rewritten as a default for v2.
Every lesson names the v1 incident, the v2 mechanism that prevents it, and the v1 source lines it comes from. Process rules (self-tests, three states, exit codes, timeouts, strict CLIs) are in [`engineering-rules.md`](../engineering-rules.md) and are not repeated here.
v1 deleted and rebuilt its warehouse twice (2026-08-07, 2026-08-21). Read its numbers as orders of magnitude, always together with the population they were measured on.

**Evidence tags:** ✅ measured or verified · ⚠️ from documentation · ❓ unverified · `measured on v1, <date>` = measured on v1's own DuckDB warehouse. Code names follow [`CONTEXT.md`](../../CONTEXT.md).

## Contents

1. [Point-in-time and look-ahead](#1-point-in-time-and-look-ahead) - lessons 1-6
2. [Sources and lineage](#2-sources-and-lineage) - lessons 7-11
3. [Coverage and truncation](#3-coverage-and-truncation) - lessons 12-17
4. [Units, scale and signs](#4-units-scale-and-signs) - lessons 18-21
5. [Thresholds and denominators](#5-thresholds-and-denominators) - lessons 22-26
6. [Tests that lie](#6-tests-that-lie) - lessons 27-33
7. [Aggregation and comparison](#7-aggregation-and-comparison) - lessons 34-38
8. [Storage, recovery and history](#8-storage-recovery-and-history) - lessons 39-41
9. [Freshness and lag](#9-freshness-and-lag) - lessons 42-45

---

## 1. Point-in-time and look-ahead

### 1. The earliest fill after a signal at the close of T is the open of T+1
- **What happened in v1:** measuring an outcome from the close of the signal day instead of the next session's open inflated a measured forward return by about a third (✅ measured on v1, 2026-08-05).
- **In v2:** any mart that joins a setup to its outcome starts the outcome at the next session's open. The singular test `assert_outcome_starts_after_signal` checks this ordering.
- **Source:** (v1 07 §v2.2.1, L977)

### 2. A value stored for date T uses only data available at T
- **What happened in v1:** two traps. Ichimoku Senkou has a "plotted" column and a "computed" column, and storing the wrong one leaks 26 sessions of future data. Swing pivots used `rolling(center=True)`, which reads `lookback` sessions ahead (⚠️ documented trap; v1 guarded it with a truncation test).
- **In v2:** dbt window frames end at `CURRENT ROW`, and a lint check rejects `FOLLOWING`. Each indicator model gets a truncation test: deleting every row after T must leave the values at T unchanged.
- **Source:** (v1 04 §3, L86) · (v1 04 §8, L478)

### 3. Universe membership is decided from the past, and delisted symbols stay in history
- **What happened in v1:** `SELECT DISTINCT symbol FROM v_universe` took every symbol that was *ever* in the universe, so the 2015 breadth base contained only symbols that later became liquid. Indicators were missing for 14.4% of the 2015 top-150 and 0.2% of 2023 (✅ measured on v1, 2026-08-05). Prop-trading eligibility measured over the whole history was look-ahead too. A guard did work: DQ test 32 found 123 symbols that left the universe over 4,731 sessions, which proved the universe really was point-in-time. Universe churn (238/364 = 65.4%) is not the delisting rate.
- **In v2:** `adv_20d_vnd` is computed `ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING`, and eligibility windows end at the previous session. The test `assert_universe_has_exits` requires the number of symbols leaving the universe to be > 0. `dim_security` keeps delisted symbols with their listing dates. A table name never proves that its contents are point-in-time.
- **Source:** (v1 07 §v2.5.10, L1442) · (v1 07 §v2.2.5, L1043) · (v1 06a §v1.7.9, L514) · (v1 PLAN_load_fundamental §13.1, L568) · (v1 05 §2, L129) · (v1 07 §7.1, L315) · (v1 11 P8, L73) · (v1 10 GĐ0, L55) · (v1 01 §3, L92) · (v1 _tham_khao, L137)

### 4. Disclosed data is joined on `available_from_date`, derived from the legal deadline
- **What happened in v1:** joining on the end of the reporting period leaks figures that had not yet been published. The vendor gives no publication date. v1 set Q1/Q3 = +30 days, Q2 = +60, Q4/annual = +90, plus a 5-day buffer (⚠️ Circular 96/2020). Against 842 real news dates, the median lag was 31 days and 99.8% were ≤ 90 days (✅ measured on v1, 9 symbols). Per-symbol news dates were rejected because uneven precision is itself a bias.
- **In v2:** a seed `disclosure_deadlines` with `effective_from`/`effective_to` columns. The singular test `assert_no_join_before_available_from` fails if any joined row has `available_from_date > trade_date`. The publication lag is a declared assumption, never a measured fact.
- **Source:** (v1 06 header, L1) · (v1 06 §1.2, L20) · (v1 06a §v1.6.5, L96) · (v1 06 §6b.4, L435) · (v1 02 §11.1, L281) · (v1 _tham_khao, L137)

### 5. Share counts are a time series; a "today" count is never applied to the past
- **What happened in v1:** the vendor returns today's `issue_share`. Applied to 2018, it overstates HPG ×5.6 (✅ measured on v1). The error always inflates heavy diluters. Only 366/739 (49.5%) of historically traded HOSE+HNX symbols had a share count (✅ measured on v1, 2026-08-22).
- **In v2:** share counts carry `is_shares_pit`. History marts read only rows where it is TRUE, and missing counts stay NULL (never back-filled from today).
- **Source:** (v1 06 §1.2 v1.2, L31) · (v1 PLAN_TONG_THE "Còn phải làm 08-22", L2777)

### 6. Valuation ratios are recomputed from our own prices × point-in-time shares
- **What happened in v1:** a lag scan of the vendor's `marketCap` peaked at ρ = 0.720 at +105 days after period end. That is later than v1's own availability date, so it is about 70 days of look-ahead (✅ measured on v1, 2026-08-04). The first scan had used a hard ρ > 0.85 cutoff and missed it: the single-peaked curve was the evidence, not the peak value.
- **In v2:** vendor `pe`, `pb` and `marketCap` are never staged as facts. `market_cap_vnd` = close × point-in-time shares, computed in dbt.
- **Source:** (v1 06a §v1.6.8, L164) · (v1 06 §v1.6, L101)

## 2. Sources and lineage

### 7. Each dataset has one primary source, enforced per (symbol, trade_date)
- **What happened in v1:** history from a legacy file (adjusted as of 2026-03) was joined to a VNDirect tail (adjusted as of today). This made fake 50% jumps at the seam for 297/694 symbols (42%) (✅ measured on v1, 2026-08-03). By 2026-08-19 the problem had grown to 275 symbols with interleaved sources, up to 36 switches each (✅). `is_stale` hid the problem, not the universe. Two sources were both "primary" because one used `role: primary` and the other `is_primary: true`. The fallback was not equivalent either: VNDirect had 1-VND resolution, so 54.4% of its 96,497 rows sat off the 10-VND grid against 0% for vnstock. A restore from a copy brought back more contamination (96,497 rows against 295).
- **In v2:** `sources` is a seed with exactly one `role` vocabulary (`primary`/`fallback`/`verifier`). The test `assert_one_primary_per_dataset` enforces one primary. A unique test on `(symbol, trade_date)` in staging means two sources can never fill the same row. A secondary source is used only for reconciliation, never spliced in. When a corporate action changes the adjustment anchor, the symbol's whole history is reloaded from the primary.
- **Source:** (v1 03 §5 R8, L318) · (v1 02 §v1.2, L391) · (v1 00_INDEX v2.7.1, L122) · (v1 03 §v2.7.1, L770) · (v1 03 §v2.7.8, L846) · (v1 PLAN_TONG_THE §2.41, L346) · (v1 PLAN_TONG_THE §2.39, L3304) · (v1 PLAN_TONG_THE "Khôi phục", L2904) · (v1 10 GĐ0, L55)

### 8. A declared source is verified by what actually arrives in the warehouse
- **What happened in v1:** `sources.yml` declared yfinance as the macro primary. It had delivered 0 rows, it was not installed, and 100% of rows came from a legacy export (✅ measured on v1, 2026-08-23). A lookalike ticker (CL=F) silently returned a single bar.
- **In v2:** the test `assert_every_declared_source_delivers` joins the `sources` seed to `_source_id` counts in raw. The reverse test checks that every row's `_source_id` is a declared source. A missing ticker is reported as missing, never swapped for a similar one.
- **Source:** (v1 PLAN_TONG_THE §M1, L1060)

### 9. Raw and adjusted prices are separate columns, and adjustment is only trusted when it can be checked against raw
- **What happened in v1:** all three sources were adjusted (`is_adjusted: true`), and `close_raw` was 100% NULL (4,533,744 rows; ✅ measured on v1, 2026-08-19). Corporate-action data covered 16 months against 26 years of prices. As a result, v1 **could never validate its adjustment**, and its ceiling/floor counts and limit-lock detection were estimates. One conclusion was wrong only because "silver" was assumed to be raw.
- **In v2:** the VPS stream is the first `raw_price` source. `raw_price` and `adjusted_price` never share a column. Intraday changes use the feed's own `reference_price_vnd`, `ceiling_price_vnd` and `floor_price_vnd`, never the adjusted close. Raw-only checks (tick grid, band, limit lock) run only on raw rows from the stream start date. ❓ Whether the feed actually carries reference/ceiling/floor fields is still to be confirmed in S0.
- **Source:** (v1 PLAN_TONG_THE §2.24, L1723) · (v1 10 1.42/2.24, L106) · (v1 02 §v1.7, L804) · (v1 07 §7.2b, L339) · (v1 03 R10 note, L410)

### 10. Reference attributes come from the official listing, and a fix is traced to every copy
- **What happened in v1:** inferring `exchange` from tick size was right for only ~27% of 1,549 symbols (✅ measured on v1, 2026-08-03). The vendor sends `HSX`, not `HOSE`. After the fix, one model still read the old column, and a `SELECT i.*` view overwrote the corrected one. The result was 260,054 rows (21.9%) with the wrong exchange, all in one direction (73 HNX symbols labelled HOSE), and every structural test passed (✅ measured on v1, 2026-08-05).
- **In v2:** `exchange` comes only from the listing source, normalised in staging, with an `accepted_values` test. Marts select explicit columns, never `*`. After a source fix, dbt lineage (`dbt ls --select <model>+`) lists every downstream model to check.
- **Source:** (v1 01 §3, L92) · (v1 10 1.19, L91) · (v1 03 §5 R19, L329)

### 11. Corporate actions are detected from the official ex-rights calendar, not from return thresholds
- **What happened in v1:** a test of "|return| > band without a corporate action" hard-coded 7%/10%. It raised false positives on first listing days, after long suspensions, and on `ex_rights_date`, when bands widen to ±20% (HOSE) and ±30% (HNX) (⚠️ documented).
- **In v2:** `corporate_action` rows come from the official calendar. The abnormal-move test reads `price_band` from the `market_rules` seed, which has `effective_from` and an ex-date case, and it lists its exemptions explicitly.
- **Source:** (v1 09 §2.3, L182) · (v1 03 §6.3, L561)

## 3. Coverage and truncation

### 12. Sources truncate silently, so coverage is measured and blocks the write
- **What happened in v1:** `foreign_trade` returned only the latest 100 rows by default, with a server cap of 1,000 behind that. A 2015-2026 load got 400/2,891 sessions (13.8%), yet all 24 columns were 100% non-NULL and `matched + deal = total` held. The bronze file was overwritten anyway (✅ measured on v1). `news()` had a 90-day default window plus the 1,000-row cap.
- **In v2:** every dlt resource treats exactly 100 or 1,000 returned rows as a cap, not as data. A coverage gate (distinct `trade_date` against the calendar, per dataset) stops the load before it writes. A NULL rate never proves completeness: truncated data is *missing rows*, not empty cells.
- **Source:** (v1 03 §5 R9, L319) · (v1 11 R9, L28) · (v1 02 Company.news, L761)

### 13. Missing, zero and NULL are three different values
- **What happened in v1:** an older project backtested two years on 4.5 months of foreign-flow data because the gaps were filled with a neutral default (✅ incident). Of all financial-statement line rows, 38% (2,312,059 / 6,082,786) were 0 in every period, because the cross-industry schema fills 0 for "not applicable" (✅ measured on v1). Picking the wrong revenue key gave near-universal zeros while every check stayed green; the right key was 94.9% filled, the wrong one 2.6%. Redistributing NULL values from one input into another made one column mean two things.
- **In v2:** raw keeps the vendor's 0. Staging adds a not-applicable flag and leaves those rows out of every denominator. A missing feature is NULL, and rows with NULL inputs are excluded and counted. A missing prop row means 0 only for eligible symbols. Keys are chosen by fill rate. Power BI shows a gap as blank (⚪), never as 0.
- **Source:** (v1 03 §6.4, L528) · (v1 06a §v1.6.6, L125) · (v1 06a §v1.6.3, L70) · (v1 PLAN_load_fundamental §3.5, L148) · (v1 05 §2, L129) · (v1 07 §v1.9.2, L654) · (v1 06 §6b.4, L435)

### 14. The coverage measure matches the question and the shape of the data
- **What happened in v1:** coverage per symbol passed 2,892/2,892 sessions (minimum 99.8%), yet foreign data starts on 2015-01-05, so earlier periods had breadth sessions and no foreign sessions (✅ measured on v1). TTM coverage was 89.2% weighted by period and 69.6% weighted by session, and both were right. A "shorter than the longest series" rule would have blocked CPI (30/55) on every run. Session and symbol thresholds (0.95 / 0.90) had once shared one name.
- **In v2:** separate tests for session coverage, symbol coverage and period coverage, each with its own config key. Daily series on a shared calendar use a ratio. Sparse or annual series use "never shrinks from the stored count". Snapshot series use overlap. The period in progress is exempt.
- **Source:** (v1 08 §v2.7.2 B, L502) · (v1 08 §v2.9.31 C, L839) · (v1 06a §v1.7.6, L422) · (v1 PLAN_load_fundamental §11, L481) · (v1 11 R9, L28) · (v1 PLAN_TONG_THE §M3, L1230)

### 15. Coverage is checked across liquidity tiers, including the coverage of any cross-check
- **What happened in v1:** foreign rows were missing for symbols with about 28× lower median traded value, so waiting would not fill the gap (✅ measured on v1, 2026-08-06). Prop-trading coverage was 77.1% / 46.5% / 17.5% across the HIGH / MEDIUM / LOW liquidity tiers. A prop-trading witness covered only 973 large caps, so 100% of the 324 small-cap violations had nothing to compare against.
- **In v2:** coverage reports are grouped by liquidity tier and `exchange`. Before a reconciliation is trusted, its first section reports the witness's coverage on the rows being checked.
- **Source:** (v1 PLAN_TONG_THE §2.37, L3298) · (v1 07 §v1.9.2, L654) · (v1 03 R11 note, L468)

### 16. Snapshot-only sources are accumulated from the first day
- **What happened in v1:** commodity prices and deposit rates had no history (a rolling window of about one year, or snapshots). Every missed session was lost forever. One snapshot carried a per-bank `time`, so grouping by `time` produced a "median" of a single bank on an old date (✅ measured on v1, 2026-09-22).
- **In v2:** snapshot datasets are append-only raw with `_ingested_at`. The intraday stream counts as snapshot data: what the collector misses cannot be fetched again. Grouping uses the whole snapshot, stamped with its capture time.
- **Source:** (v1 02 §11.1, L281) · (v1 PLAN_TONG_THE §M5, L1664)

### 17. Every input's coverage start is checked before a period is analysed
- **What happened in v1:** fundamentals started on 2018-05-07 and a multi-input feature set was complete only from 2020-03-02, so every earlier period had silently used fewer inputs than assumed (✅ measured on v1, 2026-08-14). Correlations were computed before filtering for coverage.
- **In v2:** a seed `dataset_coverage` (dataset, `coverage_start`, symbol scope). Marts that combine datasets expose the latest coverage start, and Power BI greys out the periods before it.
- **Source:** (v1 07 §v2.8, L2024) · (v1 03 §6.4, L528) · (v1 07 §v2.6.7, L1760)

## 4. Units, scale and signs

### 18. Prices are integer VND, and scale is detected against data already stored
- **What happened in v1:** VNDirect and DNSE send thousand VND (28.5 = 28,500), while vnstock may send VND. A ×1,000 error passes every structural check (⚠️ documented, v1 guarded it). v1 took the median ratio to existing rows on overlapping sessions: ~1 means VND, ~1,000 means thousands, and anything else means a different adjustment anchor, not a unit problem.
- **In v2:** `_vnd` columns are INTEGER. The test `assert_price_scale_matches_history` compares the median ratio to the previous load. `_pct` (×100) and `_ratio` follow spec §13.2 and are never mixed in one column.
- **Source:** (v1 02 §v1.2, L417)

### 19. Units are confirmed by at least two independent witnesses before use
- **What happened in v1:** financial-statement units were confirmed in three independent ways: the implied share price (median 13,700), HPG revenue magnitude, and revenue ÷ traded value (median 15.16). Share units were confirmed by our market cap against the vendor's at a median of 0.876 over 35,505 pairs: a lagged field misses by tens of percent, never by ×1,000 (✅ measured on v1). 33/56 macro series still had unverified units.
- **In v2:** a seed `units` marks each measure `is_unit_verified`, and Power BI labels unverified measures. A field rejected for timing can still serve as a unit witness.
- **Source:** (v1 06a §v1.6.4, L88) · (v1 06a §v1.7.3, L357) · (v1 PLAN_load_fundamental §10.1, L376) · (v1 PLAN_TONG_THE §M5, L1664)

### 20. Logic that consumes vendor signs gives the same result for either sign
- **What happened in v1:** the vendor records expenses as negative, but inconsistently: interest expense was negative in 83.6% of rows. `interest_expense > 0` cut coverage to 0.4%; using `ABS()` raised it to 55.9% (✅ measured on v1). Flipping the sign with ×−1 would have broken the other 16.4%.
- **In v2:** formulas use `ABS()` where the vendor's sign is not consistent. The fixture for each such model has a planted pair of opposite-sign inputs that must give the same output.
- **Source:** (v1 06a §v1.7.10, L572) · (v1 PLAN_load_fundamental §13.3, L568)

### 21. Valid ranges come from the domain, and out-of-range rows are quarantined, not patched
- **What happened in v1:** a `price > 0` blocker went red on real data: WTI closed at −37.63 on 2020-04-20. Interbank 1M = 250% and 3M = 512% on 2016-01-06 were vendor typos. Bank `car` was 0 and `cir`/`llr_to_npl` were negative for all 23 banks, and nobody noticed because the columns were never displayed. `roe` and `net_margin` looked computed but were mapped from the vendor (only 37.1% matched our own formula) (✅ measured on v1, 2026-08-16 to 09-22).
- **In v2:** validity ranges live in a seed with a documented reason. Out-of-range rows stay in raw and are excluded from marts with a logged count. Known-broken columns are named in the model docs, not "fixed" with `ABS()`. Each column records in the dbt `meta` whether it is vendor-supplied or computed.
- **Source:** (v1 PLAN_TONG_THE §M4, L1272) · (v1 PLAN_TONG_THE §M5, L1664) · (v1 06a §v1.9, L762) · (v1 06a §v1.11, L832)

## 5. Thresholds and denominators

### 22. Thresholds on a growing sample are ratios, and changing a denominator means recalibrating
- **What happened in v1:** `top3_contribution > 70%` correlated with symbol count at ρ = −0.644: all 8 sessions that crossed it were in the < 150-symbol group, and 0/2,429 sessions with ≥ 150 symbols crossed it (✅ measured on v1, 2026-08-03; 2,911 sessions). A count-based market-stress threshold missed a known crash day that a ratio caught. The active universe went from 45 symbols (2018) to 153 (2025), and changing a breadth base cut a detector's accuracy until it was recalibrated.
- **In v2:** breadth and DQ thresholds are ratios or rolling z-scores. A threshold's config entry names its denominator, and changing the denominator invalidates the threshold. Liquidity concentration is not used as a proxy for index-point concentration (0/2,297 sessions).
- **Source:** (v1 04 §7.1b, L281) · (v1 04 §7.8b, L436) · (v1 11 R20, L44) · (v1 07 §v1.9.5, L787) · (v1 10 GĐ2, L428)

### 23. One threshold answers one question, and ranking happens after filtering
- **What happened in v1:** a fixed 10-billion-VND liquidity floor was 0.986% of market turnover in 2015 and 0.040% in 2025, a 24× drift. It answered both "is this tradeable?" and "is the breadth sample large enough?", which made 2013-2019 look "too thin". The fix split them (an absolute floor, and a relative top-150 base). The first version of the fix ran `ROW_NUMBER()` before filtering `exchange` and `is_stale`, so "top 150" held 107.7 symbols in 2015 (✅ measured on v1, 2026-08-05).
- **In v2:** a tradeability floor (`adv_20d_vnd`) and the breadth base are separate config keys. Ranking models filter first, and the test `assert_top_n_has_n_rows` checks the result.
- **Source:** (v1 07 §v2.5.7, L1331) · (v1 07 §v2.5.8, L1380)

### 24. Denominator floors are set per ratio, and extreme values are capped downstream, not deleted
- **What happened in v1:** one shared "profit > 100 bn VND" floor cut P/E coverage to 20.1%. Using "> 0" for P/E restored 56.2% (✅ measured on v1, 2026-08-04). The 100 bn floor is right only for cash-flow ratios, whose denominator can change sign. P/E p99 = 469 is real information.
- **In v2:** each ratio model declares its own floor in config. The data layer keeps true values, and any winsorising happens only in the consuming mart.
- **Source:** (v1 06a §v1.7.5, L407) · (v1 PLAN_load_fundamental §10.4, L435) · (v1 06 §6c, L519)

### 25. A threshold carries the measurement it was set from
- **What happened in v1:** CFO coverage was set at 95% against an actual 85.5%, so the test was red forever and then ignored. A gate that is red by design turns into a bypass ritual. Test 29 was set at 80% before anyone measured it and went red at 78.21%, because thin denominators had not been filtered (✅).
- **In v2:** every dbt test threshold has `meta: {measured_value, measured_on, population}`. A threshold nobody has measured is `warn`, never `error`. A gate that cannot pass is redesigned to measure what is actually dead.
- **Source:** (v1 03 §5 R15, L325) · (v1 PLAN_decision_engine §4, L283)

### 26. Every number states its set, its n, its aggregation and a fixed denominator
- **What happened in v1:** "close off the tick grid" was recorded as 57.98% on signal rows and 28.98% on the full table, with neither set named. Both were right, and the premise itself was retracted on 2026-08-06 (see contradictions). A sign gate shrank its own denominator by dropping zero years (5/5 instead of 5/6). A tail year that spilled into the window grew it from 6 to 7. "41.2% of planted faults caught" applied only to 17 faults at points already under suspicion (✅).
- **In v2:** reports and test messages print `x% of <set>, n = <count>`. Per-period comparisons print `active_symbol_count` beside every value. When a denominator is not known exactly, it is bracketed between two measured bounds or reported as not measured.
- **Source:** (v1 03 §5 R27, L337) · (v1 07 §v2.2.2, L1004) · (v1 07 §v2.7.4, L1877) · (v1 07 §v2.7 ④, L1998) · (v1 PLAN_TONG_THE §2.45, L3159)

## 6. Tests that lie

### 27. An empty table, a skipped check and a filter that is always TRUE are reported as "not run"
- **What happened in v1:** `COUNT(*) WHERE <violation>` on a 0-row table returns 0 and passes. A filter column was TRUE on 100% of 836,793 rows because half of its conditions had no data. v1's own status tool marked itself green with no self-test (✅ measured on v1, 2026-08-05).
- **In v2:** a generic test `not_empty` runs on every model that other tests guard. A filter column ships with the number of conditions that actually ran. A gap the project knowingly lives with is declared, and that declaration is itself a blocking test. See the three states in [`engineering-rules.md`](../engineering-rules.md#verification).
- **Source:** (v1 03 §5 R12, L322) · (v1 07 §v1.9.1, L635) · (v1 PLAN_TONG_THE "Hai nợ hoãn", L2610) · (v1 00_INDEX v2.1, L108)

### 28. One test checks one condition
- **What happened in v1:** one DQ test combined two price conditions and reported 667 violations. It took a separate tool to find 667 + 0: one branch was a fixable logic bug, the other was impossible without raw prices (✅ measured on v1, 2026-08-05). Two other tests also had to be split by exchange.
- **In v2:** each dbt test asserts one condition, and a condition that has a different remedy per `exchange` gets one test per exchange.
- **Source:** (v1 03 §5 R21, L331)

### 29. A test is itself checked on known answers before its result is believed
- **What happened in v1:** six measurement bugs in one session (✅ 2026-08-04). Examples: `set(columns)` collapsed 19 duplicate names; `select_dtypes` dropped all-NULL columns before counting them; picking the first candidate gave "identity holds in 23%" instead of 99.87%; `datetime64[us]` vs `[ns]` broke a join. Fifteen symbols all stopping at ~90 days looked like a hard limit, but every call had used the same default parameter. A failure that is too clean (exactly 1.0000, or 0.0% at every threshold) points to a bug in the test. A Q4 imputation was checked on a set with known answers against a threshold fixed in advance, and it failed (npat 69.1% < 90%).
- **In v2:** every singular test has a fixture under `tests/fixtures/` with a known answer and a control. The sub-counts in a report must add up to the total.
- **Source:** (v1 03 §5 R11, L320) · (v1 03 R11 process, L410) · (v1 02 Company.news, L761) · (v1 06a §v1.7.6, L422) · (v1 PLAN_TONG_THE §M4, L1272)

### 30. Planted faults carry the real failure mechanism, and a monitor proves it can go red
- **What happened in v1:** 10/17 planted faults slipped past the monitors, while the control group was 21/21 green. 13/21 monitors had never gone red. One audit group was 100% noise (✅ measured on v1, 2026-08-07 and 08-26). For autocorrelated series, a circular-shift placebo gave 0/40 false alarms against 12/40 for a plain shuffle.
- **In v2:** phase P3 is done only when every ported dbt test has failed at least once on a planted fault of its own mechanism. Monitors of time series are calibrated with circular-shift placebos.
- **Source:** (v1 03 §5 R31, L341) · (v1 PLAN_TONG_THE §2.45, L3159) · (v1 PLAN_TONG_THE §V2, L1422)

### 31. A test is kept only if it can come out positive
- **What happened in v1:** "do share jumps match the corporate-action table?" gave 0%, which looked like proof that nothing was wrong. But ESOP issues and private placements change share counts without an ex-date, so the test could never be positive. A gate on the daily median always measured +0.0000 and passed without having the power to see anything (✅).
- **In v2:** each test's docs state the input that makes it fail, and a fixture contains that input.
- **Source:** (v1 03 R11 note, L475) · (v1 07 §v2.7 ④, L1998)

### 32. Green data-quality checks show internal consistency; validity needs an outside reference
- **What happened in v1:** 68 green DQ checks said nothing about whether the data was right. Silver froze for four months while 54/54 validation checks passed. An identity check (DuPont, error 0.00e+00 on 705,402 rows) catches typos, not wrong data. A derived metric that "predicted" an outcome turned out to be an arithmetic identity of its own grouping variable (error 2.9e-14). The accounting identity Assets = Liabilities + Equity held for 99.87% of 37,301 pairs and earned its place as a blocker (✅ measured on v1).
- **In v2:** internal tests (dbt) are kept apart from external ones (reconciliation with v1's DuckDB, opened read-only, and vendor-to-vendor checks). Identity tests are labelled as typo guards. A metric defined from its own grouping variable is never reported as a finding.
- **Source:** (v1 07 §v2.0.6, L923) · (v1 06a §v1.11, L832) · (v1 04 §v1.9 ②, L666) · (v1 06a §v1.6.2, L56) · (v1 06 §6b.3, L415)

### 33. Grain is declared for every model and enforced by tests
- **What happened in v1:** the DDL declared primary keys, but the warehouse had 0 PKs, 0 FKs and 0 UNIQUE constraints. `CREATE OR REPLACE` dropped constraints silently. A 2-column key `(symbol, trade_date)` was unique over 4,563,534 rows and enforced one source per row (✅ measured on v1, 2026-08-16). Structural tests (not_null, unique, accepted values, relationships, freshness) and VN-specific tests (OHLC order, no missing sessions, volume ≥ 0, foreign ≤ total, room within the ownership cap) were specified but only partly enforced.
- **In v2:** BigQuery does not enforce keys either. Every model declares its grain with a `unique_combination_of_columns` test, and CI fails a model that has none. The structural and VN-specific tests are ported as dbt generic/singular tests, with relationships pointing at one security dimension. ❓ The two-source drift limit (< 0.5%) was never measured and starts as `warn`.
- **Source:** (v1 03 §v2.7.8, L813) · (v1 03 §v2.7.8 PK, L846) · (v1 03 §6.1, L496) · (v1 03 §6.2, L508)

## 7. Aggregation and comparison

### 34. Only like is compared with like
- **What happened in v1:** a measured P/E of 7.95 nearly led to a "unit error" verdict, because it was set against the market's "10-18". That range is the cap-weighted index P/E. An equal-weight median over all symbols and sessions is 9.50 and is meant to be lower; cap-weighted over the universe gave 13.24, which matches (✅ measured on v1, 2026-08-04). Refuting A does not prove B. Different holding windows are different units.
- **In v2:** measure names state their weighting (`_median`, `_cap_weighted`). Power BI never puts two weightings on one axis.
- **Source:** (v1 06a §v1.7.7, L479) · (v1 06 §6c, L519) · (v1 PLAN_load_fundamental §10.4, L435) · (v1 07 §v3.2, L2345)

### 35. Matched volume and total volume are different quantities
- **What happened in v1:** price `volume` is matched trades only, while the prop source's `total_volume` adds `put_through`. The verified relation held on 144,064 rows, with only 65% agreeing within 0.1% and the gap one-directional (✅ measured on v1). Foreign "pressure" may still mix matched and put-through trades (❓).
- **In v2:** `match_qty` and `total_qty` are separate columns, and no test asserts that they are equal. Foreign-flow marts split matched from `put_through`.
- **Source:** (v1 02 §v1.5, L611) · (v1 PLAN_TONG_THE "Còn nợ đo", L3198)

### 36. Period keys are derived from the session set and each period reports its session count
- **What happened in v1:** fixing the calendar renumbered sessions without recomputing week keys, which left 21 sessions (2012-11-23 → 2013-01-10) with a NULL `trading_week_id`. A month holds 14-23 sessions (64% spread). TTM built with `ROWS 3 PRECEDING` stretched across five real quarters when a quarter was missing. `SUM` skipped NULLs and gave 3-quarter totals. Annual ≠ the sum of 4 quarters (12/18 items matched in 2020) (✅ measured on v1).
- **In v2:** `dim_trading_calendar` derives every period key in one model, and the session sequence is a tested stable key. Every period mart has `session_count` and an `is_period_complete` flag. Rolling periods use a period index with a per-column `COUNT = 4`. Audited annual figures and quarterly figures are never mixed.
- **Source:** (v1 08 §v2.7.2 A, L453) · (v1 PLAN_TONG_THE TQ3, L940) · (v1 PLAN_load_fundamental §9.2, L317) · (v1 06a §v1.6.12, L250) · (v1 06a §v1.6.11, L302) · (v1 06 §1.2, L20)

### 37. A comparison needs a matched control and an honest sample size
- **What happened in v1:** overlapping windows shrink the effective sample to about n/K, which turned an apparently strong result into an inconclusive one; a control that did not get identical treatment distorted a comparison by an order of magnitude; autocorrelated market series need block permutation; ties were ignored by a double `argsort`; and a proportion needs a confidence interval (✅ measured on v1).
- **In v2:** in reconciliations, the control is the same query on the same partition, differing in exactly one thing; overlap-adjusted sample sizes and same-treatment controls are mandatory wherever two groups are compared.
- **Source:** (v1 07 §v2.3.1, L1058) · (v1 07 §v2.5.3, L1235) · (v1 07 §v2.9, L2113) · (v1 07 §v3.0, L2230) · (v1 07 §v2.4.1, L1132) · (v1 07 §7.3b, L402) · (v1 PLAN_TONG_THE "siết cả hai bên", L2502) · (v1 PLAN_TONG_THE "Nhịp vòng lặp", L1969) · (v1 PLAN_TONG_THE GĐ6.1, L1913) · (v1 07 §v2.6.7, L1760)

### 38. A result that fails stays failed; tolerances are never loosened to make numbers match
- **What happened in v1:** a held-out evaluation that failed was nearly relabelled "not yet run", which would have reopened it. A relative gate passed while every compared group lost money. One set of labels contradicted its own definition (❓).
- **In v2:** reconciliation tolerances are fixed before the first run. A mismatch is explained, never absorbed (see [`engineering-rules.md`](../engineering-rules.md#verification)). Outcome labels are checked against their definition before a model is blamed.
- **Source:** (v1 07 §7.5, L447) · (v1 07 §v2.6.4, L1705) · (v1 07 §v2.3.3, L1093) · (v1 07 §v2.5.6, L1319) · (v1 07 §v2.5.12, L1557) · (v1 PLAN_TONG_THE §I.5, L247) · (v1 PLAN_TONG_THE §V, L653) · (v1 PLAN_backtest §0.2, L94) · (v1 04 §7.4b, L378)

## 8. Storage, recovery and history

### 39. Backups live outside the store, are taken before each load, and cover inputs and ledgers too
- **What happened in v1:** a backup table inside the same DuckDB file was lost together with the file (2026-08-07). The first backup tool's name said "bronze", which led people to believe the decision ledgers were backed up; they were not. The older copy used for the restore was more contaminated than the lost one (96,497 secondary-source rows against 295), so the real fix was a reload from one source (✅ measured on v1).
- **In v2:** raw parquet in GCS is the backup of record, written before BigQuery. A restore is followed by the full set of dbt tests and a per-source row count, never trusted as is.
- **Source:** (v1 PLAN_TONG_THE "Còn phải làm 08-22", L2777) · (v1 PLAN_TONG_THE "Khôi phục", L2904)

### 40. Append-only evidence is never regenerated, and every gap says why it exists
- **What happened in v1:** a missing ledger session has three meanings: ran and found nothing, did not run, or was recorded and then lost. Session 2026-08-06 was lost, and today's engine would have produced 1 row where 2 had been frozen. Regenerating it would have meant inventing data (✅). A past day's score was overwritten (63.236 → 63.582). A sample run wrote 20 symbols × 7 months under the production file names, which would have replaced 3,757,955 rows.
- **In v2:** the collector writes append-only batches. A partition gap is recorded in a `partition_gaps` seed (`no_data` / `not_run` / `lost`), and the test `assert_no_undeclared_gap` blocks any gap that is not recorded. Samples and dry runs write under a `_sample` prefix.
- **Source:** (v1 PLAN_TONG_THE §2.49, L2926) · (v1 PLAN_TONG_THE "Còn nợ đo", L3198) · (v1 PLAN_TONG_THE "Còn phải làm 08-22", L2777)

### 41. Results computed from adjusted history are stamped with a fingerprint of their inputs
- **What happened in v1:** one daily load reloaded four symbols with a corporate action over 16 years. Adjusted closes changed, `adv_20d_vnd` changed, and symbols crossed the universe boundary. Five hours apart, the same run lost 25 rows and A moved by 0.0019, and 17/18 stored results went stale (✅ measured on v1, 2026-08-19).
- **In v2:** every stored analytical result records its input row count, symbol count and a content hash, and it is compared again before reuse. Marts built on `adjusted_price` are documented as retroactive.
- **Source:** (v1 PLAN_TONG_THE "Số backtest có hạn dùng", L2221)

## 9. Freshness and lag

### 42. Every load is followed by a row count per partition
- **What happened in v1:** a script reported success while VN-Index rows were never inserted. Another load wrote 698 symbols instead of about 1,030 and exited normally. Full rebuilds fail differently: the last session goes missing instead of thinning out (✅ measured on v1, 2026-08-06).
- **In v2:** per-batch message counts in BigQuery must equal the counts in parquet (phase S2). dlt loads assert the expected row and symbol counts per `trade_date`. Incremental models get a "latest session present" test, separate from a "no shrink" test.
- **Source:** (v1 03 §5 R1, L311) · (v1 PLAN_TONG_THE §2.36, L3221)

### 43. Freshness is anchored to the base layer, not to the neighbouring layer
- **What happened in v1:** silver and gold stayed frozen at 2026-03-27 while bronze reached 08-03, and every internal test passed. A view and its table froze together for 11 sessions, so their symmetric difference stayed 0 (✅ measured on v1, 2026-08-03 and 08-07). The tolerance that was measured: 0 sessions for most layers, 1 for foreign flow.
- **In v2:** each mart has a test comparing its latest `trade_date` with the raw price layer, using per-model tolerances in config. A tail-sparsity test requires ≥ 30 symbols in the last session.
- **Source:** (v1 03 §5 R7, L317) · (v1 03 R7 tests 19-21, L359) · (v1 PLAN_TONG_THE §2.42, L3034) · (v1 PLAN_TONG_THE §2.36, L3221)

### 44. Expected lag, stale-but-valid and dead are three different states
- **What happened in v1:** US series were flagged "frozen" every day although they lag by one session by design, while WTI, which really was dead, got the same flag. Index APIs lag 1-2 h (❓). Annual macro lags 8-20 months. One company's statements were 1,938 days old but correctly point-in-time; 9.65% of TTM rows were stale (✅ measured on v1).
- **In v2:** dbt source `freshness` uses a per-source expected lag from config. That constant is shared with any join window that uses it. Stale-but-valid rows keep their value plus a lag column and a flag, and are filtered downstream.
- **Source:** (v1 08 §v2.9.30 D, L756) · (v1 03 §5 R2, L312) · (v1 PLAN_TONG_THE §M3, L1230) · (v1 06a §v1.7.4, L372) · (v1 PLAN_load_fundamental §10.2, L376) · (v1 06 §6c, L519)

### 45. End-of-day loads start after a measured publication time
- **What happened in v1:** a run during the session loaded partial data. The cutoff was written as 15:00, 15:15 and 15:30 in different places (⚠️; config says 15:00).
- **In v2:** one config value, derived from "the HNX closing auction ends at 15:00" plus a measured vendor lag. dlt checks the value before extracting.
- **Source:** (v1 03 §5 R3, L313)

---

New terms used here are defined in [`../../CONTEXT.md`](../../CONTEXT.md).
