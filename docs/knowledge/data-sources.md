# Data sources - Vietnamese market data for vn-market-elt

Status: K0.2 · condensed from v1's knowledge base (KB) on 2026-10-08 · rows labelled for this file in v1's knowledge inventory.

**Evidence tags.** ✅ verified by a real call or measurement · ⚠️ from documentation or a single observation · ❓ unverified, including code-read only · `measured on v1, <date>` = measured on v1's own warehouse. That warehouse was rebuilt twice (2026-08-07, 08-21), so its numbers are orders of magnitude; the population is given with each one (INVENTORY §D).

**References.** `(v1 02 §v1.4, L494)` = v1 KB module `02_data_sources_api.md`, section, line. `sources.yml` = v1 `02_system/config/sources.yml`. `PLAN` = v1 `PLAN_TONG_THE.md`. `CL` = v1 KB `CHANGELOG.md`.

**Exchange consolidation.** From 2026-12-28 all HNX-listed stocks trade on HOSE. Every source keyed by `exchange` (index codes, per-exchange endpoints and paths) must handle the switch. Details are in `market-microstructure.md`.

---

## 1. Source landscape

- **No Vietnamese exchange or depository (HOSE, HNX, VSDC, SSC) has an open API** ⚠️ (v1 02 §1, L7). Every route is one of three:

  | Route | Examples | Trade-off |
  |---|---|---|
  | A. Broker API | SSI FastConnect, DNSE LightSpeed | Contract and ToS; needs an account, IP whitelist and yearly renewal |
  | B. Commercial vendor | FiinGroup, WiFeed | Licensed from the exchanges and normalised; paid, with unpublished prices |
  | C. Unofficial endpoints | VCI behind vnstock, VNDirect DCHART, DNSE chart-api, CafeF | Free and without ToS; can be blocked at any time; legal risk if commercialised |

- v2 uses route C through a paid wrapper: `vnstock_data` for the cold path, and the VPS WebSocket feed via `vnstock_pipeline` for the hot path.
- **Use one adapter per source** behind one extract interface, so a source swap leaves dlt and dbt untouched ⚠️ (v1 02 §1, L17).
- **Declare exactly one primary source per dataset**, and give every other source a non-writing role (fallback or drift witness). ✅ v1 incident (v1 02 §v1.2, L397; v1 03 §5, L370): the legacy store and VNDirect were both adjusted, but to different cut-off dates. After a 2:1 split, the splice showed a false 50 % jump that every structural check passed. `measured on v1, 2026-08-03`: 297/694 symbols (42 %) had a `corporate_action` within five months.
- **Prove a declared source with rows.** `measured on v1, 2026-08-23/26`: `yfinance` and `world_bank` were declared `primary` with 0 rows and no caller (v1 08 §v2.9.31 A, L815). Count rows per declared source.
- Candidate grains, designed but never enforced in v1 ❓ (v1 03 §3.1, L71):
  - daily price per `symbol` × `trade_date`;
  - index per `index_code` × `trade_date`;
  - `foreign_flow` and `prop_` per `symbol` × `trade_date`;
  - the trading calendar;
  - index constituents (SCD2);
  - the margin-ineligible list per quarter.

## 2. vnstock / vnstock_data

**Libraries and plan**
- A paid sponsor plan unlocks four libraries ✅ (v1 02 §v1.2, L456):
  - `vnstock_data`: the history and reference data source;
  - `vnstock_ta` and `vnstock_news`;
  - `vnstock_pipeline`: parallel extract and the stream client.
- Navigate the API with `show_api()` and the vendor guide `github.com/vnstock-hq/vnstock-agent-guide`. Introspection does not work: signatures are wrapped as `(self, *A, **B)`, and `dir()` omits `Market` and `Macro` ✅ (v1 02 §v1.2, L475; §v1.4, L489).
- Other libraries ⚠️ (v1 02 §4, L83):
  - `vnstock3` is a zombie package, merged into `vnstock` in 01/2025;
  - `vnquant` is for cross-checks only;
  - the SSI SDKs were last updated in 06/2024.
- The licence covers personal, research and non-commercial use ⚠️ (v1 02 §3, L48). Publish code, not data.

**Call conventions**
- **Pass `source=` on every class.** Without it, `Listing().all_symbols()` raises `ValueError: requires a data source` ✅ (v1 02 §v1.2, L469).
- Use `Company.overview()`; `profile()` does not exist. Request `put_through` as `board='put_through'` on `price_board()` / `trade_history()` ✅ (L471-472).
- Pin the call path. The library has three call styles whose signatures changed across versions; v1 probed them once, then locked one in ✅ (v1 02 §v1.2, L419).
- Set timeouts above the first call, which includes vnai authentication. `measured on v1, 2026-08-16`, one machine: first call 19.57 s, later calls 0.22-1.5 s (sources.yml L548).
- Treat N consecutive errors as "source down". `measured on v1, 2026-08-17`: VCI returned 66 socket timeouts in 66 calls over 36 min, and no check fired. v1 used N = 20 (sources.yml L649-669).

**Silent row caps on `Trading`** ✅ (v1 02 §v1.4, L494; v1 03 §5, L385)

| Layer | Mechanism | Handling |
|---|---|---|
| 1 | Default **100 rows**: the latest 100 sessions; the rest is dropped silently | Pass `limit=`. Of 18 parameter names tried, it is the only one that works |
| 2 | Server hard cap of **1,000 rows** (`limit=20000` still returns 1,000) | Slice requests to ≤3 years (~750 sessions) |

- Defend in three layers:
  1. probe the date range before loading;
  2. treat exactly 100 or 1,000 rows as "cap reached";
  3. **block the write** when distinct `trade_date` ÷ calendar sessions < 0.95.

  Only layer 3 works without knowing the cap mechanism. Truncation means missing rows, not NULL cells, so measure coverage on rows (v1 03, L413).
- `Company.news()` has a default 90-day window (widen it with `start=`), caps at 1,000 rows per call, and pages backwards with `end=`. `Finance` has no row cap ✅ (v1 02 §v1.6, L726, L761).
- `Company.events()` (VCI) returns **the latest 50 events of every kind** by default. Insider deals crowd out dividends, so one symbol's dividend history began two months ago. Filtering `event_codes="DIV,ISS"` and paging (`size=100`) reaches 2006-2009 with an exercise ratio on every row ✅ `measured on v2, 2026-10-21`, 20 symbols, then 5 paged.

**Vietcap REST, called directly** (`vnmarket.el.load_vci_reference`, config `vci_rest`)
- **PyPI quarantined `vnstock` and `vnai` on 2026-09-24**, pending a "security review" whose reason is unpublished; fresh installs fail. v2 does not depend on either.
- Read in v1's installed copy (source only, never imported), the libraries do the following on import ✅ `read on v2, 2026-10-21`:
  - write AI-assistant instruction files (`./AGENTS.md`, `~/.cursorrules`, `~/.windsurfrules`, `~/.clinerules`, `~/.clauderc`, `~/.github/copilot-instructions.md`, `~/.gemini/config/AGENTS.md`) with text fetched from the vendor's server;
  - send usage telemetry every 300 s.
- The two endpoints v2 needs are public and take plain HTTP with browser-like headers:
  - `iq.vietcap.com.vn/api/iq-insight-service/v1/events` (paged, with `totalElements`);
  - `trading.vietcap.com.vn/api/price/symbols/getByGroup?group=VN30`.

  Every call has a timeout and is paced at 3 s. At 1.5 s the events endpoint stopped answering after ~250 calls (read timeouts that lasted past the run) `measured on v2, 2026-10-21`, so a failed call is retried after 60 / 180 / 600 s, and 5 calls that fail every retry stop the run.
- Corporate actions: one snapshot per run, refused when a symbol's rows differ from `totalElements` or fall below the newest snapshot (rule 9).
- Index membership: **today's list only**, VN30 and HNX30 (VNDIAMOND returned empty 2026-10-21). The ledger starts 2026-10-21. A missed session is lost, so the daily chain records it every session.

**Financial statements** (loaded as `raw_vnstock.fundamental_statement`, mart `fct_fundamental_quarterly`)
- Source: v1's VCI extract, long form. Quarterly and yearly from 2018 Q1; 1,549 symbols; 18 income-statement, 43 balance-sheet, 14 cash-flow and 55 ratio items ✅ `measured on v2, 2026-10-21` (the file v1 wrote on 2026-08-22). v1's extractor is not in its daily chain, so the file is a snapshot that changes only when someone reruns it.
- **No publication date.** A quarter is usable from its statutory deadline + 5 days (seed `fundamental_availability`, Circular 96/2020/TT-BTC):
  - Q1 and Q3: 30 days;
  - Q2: 60 days (reviewed half-year);
  - Q4: 90 days (audited annual).

  The source's figures are the **final** ones, so Q4 uses the audited deadline, not the 30-day unaudited one. v1 measured 842 announcements across 9 symbols: median 31 days, p95 76, 99.8 % within 90 ✅ (v1 06a §v1.6.5). dbt recomputes the date and reconciles it with v1's own column on every row.
- **Zero trap:** the source writes 0 for an item that does not apply. 43 % of values are 0. An item that is 0 in every period of a symbol becomes NULL ✅ (v1 06a §v1.6.6; v1 decides per industry, v2 per symbol).
- **Operating cash flow is not in the source.** It is derived as change in cash - investing - financing - FX. Cash is the balance-sheet line named after the bank template (`Tiền, vàng gửi tại các TCTD khác`), which equals cash + equivalents for 100 % of non-bank rows, so adding the parts too would count cash twice ✅ (v1 06a §v1.6.12). Banks get NULL. `measured on v2, 2026-10-21`: 84 % of quarters derive; the median 4-quarter cash conversion is 0.93.
- P/E, P/B and market cap must be recomputed from warehouse prices: the source's own price lags about 105 days ✅ (v1 06a).

**VCI vs KBS**
- Price history depth ✅ `measured on v1, 2026-08-18`, 65 symbols, 2015-01-05 → today (sources.yml L19-53):
  - both sources cover every symbol with the same adjustment cut-off;
  - VCI is deeper on 44/65 symbols, KBS on none;
  - KBS/VCI session ratio: median 87 %, worst 3 %;
  - KBS has almost nothing before 2015-09-28.

  ⇒ Keep VCI first and KBS as the price fallback. This is one day's measurement.
- **Pin `source="VCI"` for flows.** `Trading` history (`foreign_trade`, `prop_trade`) exists only on VCI. `KBS.foreign_trade()` succeeds but returns a 10 × 11 price-board **snapshot**, so a rotating `["VCI", "KBS"]` adapter would load the wrong data silently ✅ (v1 02 §v1.4, L510).
- VCI endpoints for debugging ✅ (v1 02 §3, L74):
  - `trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart`;
  - `.../api/market-watch`;
  - `iq.vietcap.com.vn/api/iq-insight-service/v1/{events,market-indices,company}`.

  vnstock 4.0.0 had to fix WAF blocking on these endpoints, so keep a price fallback ⚠️ (L79).

**Prices are already adjusted**
- `vnstock_quote` is declared `is_adjusted: true`, per the library documentation ⚠️ (sources.yml L60). Store its prices as `adjusted_price`, whatever the layer name.
- Read the source declaration before treating a table as a reference ✅ (v1 03, L461). A wrong `tick_size` conclusion once came from assuming silver held `raw_price`.
- No source in v1's stack provides `raw_price` (v1 never stored raw prices). Adjusted history is rewritten after each `corporate_action`, and adjustments differ between sources ⚠️ (v1 _tham_khao, L226; v1 02 §15, L677).

**Price-scale detection**
- DCHART and DNSE return thousands of VND (28.5 = 28,500); vnstock may return VND. A 1,000× error passes every structural check ✅ (v1 02 §v1.2, L424).
- Compare overlapping sessions with stored data and take the median ratio (L428):
  - ~1 ⇒ VND;
  - ~1000 ⇒ thousands of VND;
  - anything else ⇒ a different adjustment cut-off: fail loudly.
- Index sources return **points** ✅ (sources.yml L188).
- The plausible implied share price is **100-5,000,000 VND**; penny stocks below 1,000 VND are real ✅ (v1 06, L57).
- Same field, two units ✅ `measured on v1, 2026-08-04` (v1 06, L57). `KBS.overview().charter_capital` is in **billion VND**, while `capital_history()` reports it in VND. Dividing the billion figure by the 10,000 VND par cut market-cap coverage to 21 %.
- Take shares from `issue_share`, then `outstanding_shares`, then charter capital ≥ 1e9.
- Tick-grid test: an implied price (value ÷ shares) on the `tick_size` grid means both inputs are real observations ✅ `measured on v1` (v1 06a §v1.6.7, L145). For `numberOfSharesMktCap`, 87.7 % of implied prices are multiples of 10 VND, against ~10 % by chance.

**Dead, snapshot-only or NotImplemented** ✅ `measured on v1, 2026-08-03/04` (v1 02 §v1.4, L559; §v1.6, L741)

| Method | Status |
|---|---|
| `Company.capital_history()`, `insider_trading()` | `NotImplementedError`; get point-in-time shares from `numberOfSharesMktCap` in `Finance.ratio()` |
| `Listing.disclosures()` (VCI, KBS) · `Listing.history()` | `NotImplementedError` inside a misleading `RetryError` · a wrapped `AttributeError` |
| `Trading.order_stats`, `side_stats`, `trading_stats`, `matched_by_price` | `RetryError` |
| `Finance.note()`, `Finance.history()` | fail on VCI and MAS |
| `Company.overview()` | **today snapshot**: `issue_share` is not point-in-time |
| `Company.events()` | `public_date` 2015-02-26 → 2026-07-07: use it for `corporate_action` timing; it has **no** financial-statement dates (0/159 rows) |
| `Trading.insider_deal` | works, 2018-12-18 → today, with `public_date` |
| `Market.price_board` / `quote` foreign fields | today snapshot only |

**TCBS is dead** ✅ (v1 02 §8, L224; sources.yml L673)
- Its endpoints return 404 (`/tcanalysis/v1/ticker/FPT/overview`, `/stock-insight/v2/stock/bars-long-term`).
- vnstock removed TCBS in v3.5.0 (2026-03-07). Ignore tutorials built on `apipubaws.tcbs.com.vn`.

## 3. Intraday stream feed (not yet measured, ❓)

- **Source:** a broker's WebSocket market-data feed, reached through the
  `vnstock_pipeline` sponsor library. Nothing has been run yet; spec step S0 is
  the first measurement.
- **Message families:** indices, market aggregates, per-symbol quotes, the order
  book (HOSE), foreign flow, put-through and odd lots. Subscription is per symbol.
- **Silence is the failure mode:** a stalled feed raises no error, so the
  collector alerts on the stale threshold in `config/collector.yml`.
- **Licensing:** the sponsor library is licensed per device, counted per
  operating system. Run the collector on a VM with a persistent disk and
  register each machine in its own right (ADR-0007). Vendor-internal details of
  the library are deliberately kept out of this public repository.

**Raw vs adjusted** (L804, L813)
- Intraday prices are real traded prices; adjustment happens later, when vendors rewrite history. Storing each day's close from the feed builds the lineage's **first `raw_price` series**, forward only (INVENTORY §E).
- The feed and `vnstock_quote` measure different things. On an `ex_rights_date`, "% vs yesterday" from the adjusted close is wrong; compute it against the feed's own `reference_price_vnd`.
- Intraday-only data that is not captured is lost forever, as with `put_through` snapshots (v1 10 §1.34, L116).

## 4. Foreign and proprietary flow sources

**Use VCI only.** `Trading(source="VCI")` is the only source with history ✅ (v1 02 §v1.4, L510; §v1.5, L600). `foreign_trade` goes back to at least 2015. `prop_trade` starts in **2020**; requests for 2015 and 2018 return `RetryError`.

**Matched / deal / total split** ✅ (v1 02 §v1.4, L524)
- `foreign_trade` returns 25 columns: `fr_{buy,sell,net}_{volume,value}_{matched,deal,total}`, room columns (`fr_total_room`, `fr_current_room`, `fr_owned`, with percentages) and `trading_date`.
- `_matched` is the `match` part and `_deal` the `put_through` part. Build `foreign_flow` pressure on `_matched`.
- The room columns give three independent estimates of daily shares; on HPG they agreed within 2 × 10⁻⁸. Accept a value when at least two agree within 0.1 %.
- `prop_trade.total_volume` is match **plus put-through**, while OHLCV volume is match only. The gap is by definition, so never test the two for equality ✅ `measured on v1`, 144,064 rows (v1 02 §v1.5, L625).
- Two consistency checks passed ✅ `measured on v1`, 145,272 rows (v1 05 §2, L170):
  - `prop_buy_vol_total / total_volume == prop_buy_vol_pct` exactly;
  - `matched + deal == total`, except 6,578 rows (4.53 %) NULLed by a zero trap.

**Prop gap 2022** ✅ `measured on v1, 2026-08-04` (v1 05 §2, L140; v1 02 §v1.5, L586)
- Exactly **50 sessions** are missing: 2022-03-03 → 04-29 and 2022-05-04 → 05-16.
- `foreign_flow` is complete on those days, so the gap is at the source. It matches HOSE's stop of prop disclosure on 2022-03-01 ⚠️.
- Coverage: 79.9 % in 2022, 100 % in every other year from 2020 to 2026.

**Prop coverage falls with liquidity** ✅ `measured on v1, 2026-08-04`, 145,293 rows, 973 symbols, 2020 → 2026-07 (v1 05 §2, L95)
- Share of sessions with a row, by ADV20 quintile: 26.0 % → 1.8 % → 0.6 % → 0.3 % → 0.1 %. The top ten symbols reach 96.5-97 %; 58 symbols hold 54 % of rows.
- Missing rows mean no prop trading. Use 0 for symbols that are eligible point-in-time and NULL for the rest; model `prop_` as a nullable, best-effort table (v1 05, L178).
- Fetch all symbols anyway: 85 % return nothing, but a list of "symbols that once had prop" would hide new ones. Prop takes ≈ 4.46 s per symbol, about 8× slower than foreign ✅ `measured on v1, 2026-08-25` (sources.yml L616-639).

**`put_through` is a snapshot** ✅ (v1 02 §v1.4, L552). `symbol='HPG'` returns 402 rows for the whole market, with today's tick times; `start` and `end` are ignored. Capture the whole market once per session after the close; coverage starts on the first capture day.

**Foreign flow is not published for illiquid symbols** ✅ `measured on v1`, 20 sessions (PLAN 2.37, L3298)
- Coverage over symbols that actually traded was 100.0 % on all 20 sessions.
- On the short session, the missing symbols had about 28× lower median traded value. The source does not publish them; waiting does not fill the gap.
- Watch for one anomaly ⚠️: on 2025-10-28, about 4 shares of foreign flow were reported for 115 non-traded symbols (v1 10 §1.43, L107).

## 5. Fallback and secondary sources

The free UDF endpoints (`{"t","o","h","l","c","v","s"}`) need no auth and return prices in **thousands of VND** ✅ checked 2026-08 (v1 02 §5, L95; sources.yml L67-147).

| Source | Endpoint | Notes |
|---|---|---|
| VNDirect DCHART | `dchart-api.vndirect.com.vn/dchart/history?resolution=D&symbol=&from=&to=` | Adjusted (0/2,889 HPG sessions beyond ±7.5 %). **Emits the unfinished bar**, so drop it. Data from 2015-01-05. The HNX index code is `HNX`, not `HNXINDEX` |
| DNSE chart-api | `api.dnse.com.vn/chart-api/v2/ohlcs/stock?symbol=&from=&to=&resolution=1D` | Adjusted; ends at the last closed session; runs on infrastructure separate from VNDirect |
| CafeF download | `cafef.vn/du-lieu/du-lieu-download.chn` | From about 2000. Claims both adjusted **and** unadjusted series ⚠️; never loaded in v1. A candidate historical `raw_price` source ❓ |

**DCHART has 1-VND resolution** ✅ `measured on v1, 2026-08-06`, full history (CL 2.6.1, L3834; PLAN 2.39)
- 52,463/96,497 DCHART rows (**54.4 %**) are off the 10-VND grid, against 0/4,447,775 for `vnstock_quote`.
- In v2 the effect reaches `fct_price_daily` only where DCHART is the chosen source: 330 rows (99+ symbols, 2013-2023) off the 10-VND grid, 0 primary rows ✅ `measured on v2 prod, 2026-10-13`. The multiple-of-10 test therefore checks primary rows only.
- The cause is the source itself. When vnstock failed, 19 symbols were re-fetched from DCHART, and only a semantic `tick_size` test caught it.

**A fallback is not equivalent to the primary** ✅ `measured on v1, 2026-08-06` (sources.yml L67-92)
- DCHART filled 290 rows for 5 symbols vnstock had dropped, and 281 of them were `is_stale`.
- Reloading could not undo the splice. vnstock lacks those symbols after the cut-off, and DCHART starts in 2015 while 4 of the 5 listed in 2006-2013.
- Expect a fallback to differ in resolution, depth and adjustment cut-off while still passing type checks.

**Use a secondary only as a drift witness** (v1 03 §7.3, L630; §5, L370)
- Join it beside the primary and compute drift. Alert above 0.5 %, and change the primary only by a recorded decision.
- For a one-off join of two sources, compare closes over at least 40 overlapping sessions. A gap above 0.5 % flags a `corporate_action`: re-fetch that symbol's full history from one source. Both thresholds are ❓ unmeasured.
- The overlap check sees only events inside its window; a full single-source reload is the real fix.
- Measure a witness's coverage on the population under test first ✅ (v1 03, L467). Prop volume covered 0 % of 324 small-cap violations.
- Index data: v1 noted that index APIs lag 1-2 h after the close ❓ (v1 11 R2, L23). Keep a fallback, alert on a missing index session, and measure the lag.
- From 2026-05-20 to 08-10, vnstock and VNDirect closes for VNINDEX, HNXINDEX and VN30 drifted by 0.0000 % ✅ (sources.yml L167).
- v2's index history comes from v1's `bronze_index` table, one series spliced from two origins: legacy rows with no source id (VNINDEX from 2004-01-05) to 2026-03-06, then `vnstock_quote` from 2026-03-09 ✅ `measured on v1, 2026-10-15`, 22,211 rows over 5 codes. It is used as one series until a single-source reload is possible; a level break at the seam has not been checked ❓.

## 6. Official and commercial sources

- **SSI FastConnect** ⚠️ (v1 02 §6, L134)
  - `fc-data.ssi.com.vn/api/v2/`, authenticated with ConsumerID + Secret → token; needs an SSI account.
  - Requires a **static IP whitelist**, so serverless needs NAT.
  - Registration lasts **one year**. On expiry the API returns HTTP 400 `"The connection is invalid"` silently, so alert on that response and on renewal.
  - REST: `DailyOhlc`, `IntradayOhlc`, `DailyIndex`, `DailyStockPrice`, `IndexComponents`.
  - Streams: `X-QUOTE`, `X-TRADE`, `B`, `R` (foreign room), `MI`, `OL`. Pricing ❓.
- **DNSE** ⚠️ (v1 02 §7, L181-220)
  - The REST JWT is valid for 8 h; orders need an email-OTP trading token.
  - MQTT topics: `plaintext/quotes/stock/{SI,TP,tick}/{symbol}`, `.../index/MI/{marketID}` and `.../{type}/OHLC/{resolution}/{symbol}`.
  - Production host and port ❓ (the old docs return 404).
- **Commercial vendors** ⚠️ (v1 02 §9, L236)
  - FiinGroup Datafeed is the most complete. It has a dedicated prop API and `/Market/GetHoseStockv2`, with about 70 fields including room and adjusted variants.
  - WiFeed has more than 20 years of data and a free trial with a sandbox. Prices for both ❓.
  - EODHD is rejected: aggregated VWAP, 591 symbols, small caps missing (sources.yml L675).
- **Exchanges and depository** ⚠️ (v1 02 §10, L249; v1 10, L225)
  - The HOSE and HNX sites are JavaScript SPAs; fetch rule PDFs with a browser. HNX `ListData_*` may be scrapable AJAX ❓.
  - VSDC (`vsd.vn/vi/alc/82`) is the official source for foreign-ownership limits; scrape its articles.
  - Sites still showing prop data (Vietstock, 24hMoney, FireAnt) likely use the exchange's commercial feed ⚠️ (v1 02, L584).

## 7. Per-source quirks

| Source | Dataset | Role in v2 | Adjusted? | Unit | Known traps | Evidence |
|---|---|---|---|---|---|---|
| VPS WebSocket (`vnstock_pipeline.stream`) | ticks, index, breadth, foreign aggregates, `put_through`, `odd_lot` | hot-path primary | no - traded prices | ❓ (S0) | per-symbol subscription; device slot per OS; `SystemExit` at import; 120 s stall; `board` HOSE only | ❓ v1 02 §v1.7 |
| `vnstock_data` `Quote` VCI | daily OHLCV, index | cold-path primary | yes | auto-detect; index in points | history rewritten after `corporate_action`; first call ~20 s | ⚠️/✅ v1 02 §v1.2; sources.yml L55 |
| `vnstock_data` `Quote` KBS | daily OHLCV | fallback | yes, same cut-off | VND | median 13 % shallower; almost nothing before 2015-09-28 | ✅ sources.yml L19 |
| `vnstock_data` `Trading` VCI | `foreign_flow`, `prop_` | cold-path primary | n/a | VND, shares | 100/1,000-row caps; prop from 2020; 2022 gap; illiquid symbols absent | ✅ v1 02 §v1.4-1.5 |
| `vnstock_data` `Trading` KBS | - | none | - | - | `foreign_trade` returns a snapshot without error | ✅ v1 02 §v1.4 |
| `put_through` board | `put_through` | daily snapshot | n/a | - | whole market; `start`/`end` ignored; no history | ✅ v1 02 §v1.4 |
| `Company` / `Finance` VCI | shares, events, statements | cold path (P2) | n/a | mixed | `overview()` today only; `charter_capital` in billions; NotImplemented methods | ✅ v1 02 §v1.6; 06 L57 |
| VNDirect DCHART | daily OHLCV, index | drift witness | yes, to today | thousand VND; 1-VND resolution | 54.4 % off-grid; partial bar; `HNX` code | ✅ sources.yml L67; CL 2.6.1 |
| DNSE chart-api | daily OHLCV | drift witness | yes | thousand VND | none recorded | ✅ sources.yml L103 |
| CafeF download | OHLCV history | candidate `raw_price` backfill | both claimed | thousand VND | never loaded in v1 | ⚠️ v1 02 §5.3 |

## 8. Open questions (❓)

1. Does the VPS feed carry `reference_price_vnd`, `ceiling_price_vnd` and `floor_price_vnd`? What is its real latency, and is there a symbol limit per connection? (v1 02 §v1.7, L809)
2. Does the feed block non-Vietnamese IPs? The VM is in `us-central1` (L811; spec S0.4).
3. What is the sponsor plan's per-OS device limit, and how many Linux slots are free? Are client-side rate limits also enforced on the server?
4. What is the publication lag of OHLCV, flows and index data after the 15:00 close? The "1-2 h" index figure is unmeasured (v1 11 R2).
5. Does `vnstock_quote` emit a partial bar for the running session? It is declared `unknown` (sources.yml L61).
6. Does CafeF's unadjusted download hold true `raw_price` from 2000 to today?
7. What is the first date of VCI `foreign_trade`? v1 wrote "≤2015" without measuring it.
8. How will each source key HNX symbols and HNX-Index after 2026-12-28?
9. What explains the 17 counter-examples to "foreign put-through ⇒ source volume > ours"? Why did exact volume matches fall from 66.1 % to 27.8 % between 2020 and 2026? (v1 02 §v1.5, L651)

## 9. Sources

v1, read-only:
- KB `02_data_sources_api.md`: §1 L7, §3 L39, §4 L83, §5 L95, §6 L134, §7 L181, §8 L224, §9 L236, §10 L249, §15 L665; §v1.2 L391/L456, §v1.4 L487, §v1.5 L580/L611, §v1.6 L714, §v1.7 L782.
- Other KB modules:
  - `03_data_architecture_etl.md` L71/L370/L385/L461/L630;
  - `05_flow_sentiment.md` L95-183;
  - `06_fundamental_valuation.md` L57;
  - `06a_fundamental_data_contract.md` L145;
  - `08_bi_semantic_dashboard.md` L815;
  - `10_roadmap_backlog.md` L107/L116/L225;
  - `11_quy_tac_van_hanh.md` L23;
  - `_tham_khao/2026-08-16_kpi_chart_phan_tich_CK_VN.md` L226.
- Logs and config: `CHANGELOG.md` L3834; `PLAN_TONG_THE.md` L3298; `02_system/config/sources.yml`.

URLs:
- vnstock: [GitHub](https://github.com/thinh-vu/vnstock) · [PyPI](https://pypi.org/project/vnstock/) · [licence](https://vnstocks.com/onboard/giay-phep-su-dung) · [agent guide](https://github.com/vnstock-hq/vnstock-agent-guide)
- SSI: [FastConnect API list](https://guide.ssi.com.vn/ssi-products/tieng-viet/fastconnect-data/danh-sach-cac-api) · [streaming](https://guide.ssi.com.vn/ssi-products/tieng-viet/fastconnect-data/du-lieu-streaming)
- DNSE: [LightSpeed API](https://hdsd.dnse.com.vn/san-pham-dich-vu/dnse-lightspeed-api) · [MQTT topics](https://hdsd.dnse.com.vn/san-pham-dich-vu/lightspeed-api-truoc-krx/iii.-market-data/2.-dac-ta-thong-tin-cac-message/2.2.-topics)
- FiinGroup: [Datafeed](https://datafeed.fiingroup.vn/) · [prop API](https://datafeed.fiingroup.vn/api-giao-dich/tu-doanh)
- Others: [WiFeed](https://www.wigroup.vn/wifeed) · [CafeF download](https://cafef.vn/du-lieu/du-lieu-download.chn) · [VnEconomy: HOSE stops prop disclosure](https://vneconomy.vn/lanh-dao-hose-len-tieng-ve-viec-dung-cung-cap-thong-tin-giao-dich-tu-doanh.htm) · [AlgoTrade Hub](https://hub.algotrade.vn/knowledge-hub/api-tren-thi-truong-chung-khoan-viet-nam/)

New terms used here are defined in [`../../CONTEXT.md`](../../CONTEXT.md).
