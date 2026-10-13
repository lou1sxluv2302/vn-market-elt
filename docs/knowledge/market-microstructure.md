# Market microstructure - HOSE and HNX

Status: K0.2 translation of v1 KB rows labelled for this file in v1's knowledge inventory · Written 2026-10-08 · v1 rules `as_of` 2026-08-03.

**Evidence tags.** ✅ verified · ⚠️ documentation or news (secondary unless a primary source is linked) · ❓ unverified · `measured on v1, <date>`. v1 marked some ⚠️ facts "Medium confidence"; that is noted as *(Medium)*. **Source refs.** `(v1 01 §3, L54)` = v1 KB file `01_market_microstructure.md`, section, line. `v1 yml` = `references/market_rules.yml`. Other v1 files: `03` data architecture, `04` technical analysis, `06` fundamentals, `09` agent spec, `10` roadmap, `kpi` = `_tham_khao/2026-08-16_kpi_chart_phan_tich_CK_VN.md`.

**Conventions.** Prices are integer VND (`_vnd`). Timestamps are UTC (`_at`). Dates and session clock times are Vietnam time (UTC+7, no daylight saving): 09:00 ICT = 02:00 UTC, 15:00 ICT = 08:00 UTC. Every market figure here is a dated snapshot; refresh it before relying on it (v1 kpi Risks, L248).

---

## 1. Exchanges and scope

- **In scope: HOSE and HNX listed stocks.** UPCoM is declared in the rule seeds (bands, ticks) so lookups never fail on an UPCoM symbol, and is filtered out of the universe by `exchange`, not by leaving its rules undefined. ⚠️ (v1 01 §3 v1.2, L75; v1 yml L170)
- **Normalise exchange names** from sources: `HSX` → `HOSE`, `UPCoM` → `UPCOM`, `DELISTED` → null. ⚠️ (v1 01 L95; v1 yml L173)
- **Take `exchange` from the listing source.** Tick size cannot identify the exchange: UPCoM and HNX share a flat 100 VND tick. `measured on v1, 2026-08` (v1 01 L92)
- **Keep delisted symbols** in the security dimension and build the universe point-in-time: `listed_date <= d < coalesce(delisted_date, '9999-12-31')`. Dropping them creates survivorship bias. ⚠️ (v1 01 L98; v1 03 §7.2, L619)
- **Use an internal `security_id`.** Join price history across symbol changes through it, not through `symbol`; record changes as (old symbol, new symbol, effective date). A merger ends the absorbed symbol's series. ⚠️ (v1 03 §7.2, L619)

### 1.1 HNX → HOSE consolidation (announced, not yet executed)

VNX (Vietnam Exchange) announced on 2026-09-30 ⚠️ ([VOH](https://voh.com.vn/kinh-te/co-phieu-niem-yet-hnx-se-chuyen-toan-bo-sang-hose-tu-cuoi-thang-122026-671087.html), [KTCK](https://kinhtechungkhoan.vn/vnx-cap-nhat-lo-trinh-sap-xep-lai-thi-truong-co-phieu-diem-nhan-la-phan-bang-tai-hose-1390806.html)):

| Date (2026) | Event |
|---|---|
| 12-23 (Wed) | Last HNX trading day for all HNX-listed stocks |
| 12-24, 12-25 | Those stocks are suspended; the market stays open for HOSE |
| 12-28 (Mon) | First trading day of the moved stocks on HOSE; all listed stocks trade on HOSE |

- Legal basis cited in the press: Circular 69/2023/TT-BTC (amending 57/2021); a "Circular 139" is also mentioned. ⚠️
- HNX refocuses on UPCoM, carbon credits and startups. HOSE plans two boards, premium and standard, with criteria from Decree 155/2020. ⚠️
- VTV (2026-10-06): exact timing depends on system testing. Treat the dates as announced. ⚠️ ([VTV](https://vtv.vn/chuyen-toan-bo-co-phieu-hnx-sang-hose-trong-2026-nghien-cuu-giao-dich-xuyen-trua-100261006194652428.htm))
- Under study, no timeline: continuous trading through lunch, wider price bands, settlement shorter than T+2. ⚠️ (VTV)

**What v2 does about it:**

1. Model `exchange` per symbol as **SCD2** (`effective_from` / `effective_to`); moved symbols get a HOSE row with `effective_from = 2026-12-28`. v1 already required this for single-stock exchange moves, because the band changes. ⚠️ (v1 03 §7.2, L619)
2. Look up bands, ticks and sessions by **(exchange on that date, date)**, never by the symbol's current exchange.
3. Do not add 2026-12-24/25 to the holiday seed. They are **symbol suspensions**, not market closures; HOSE trades both days.
4. "HOSE + HNX" scope stays correct for history; after 2026-12-28 it means "HOSE, including former HNX stocks".
5. Re-verify sections 2-4 and 9 when VNX publishes the final rules. Ticker codes, HNX-Index/HNX30 and post-move bands and ticks are open (§13).

## 2. Trading sessions

Clock times ICT; valid since KRX go-live 2025-05-05. ⚠️ (v1 01 §2, L31; v1 yml L16)

| ICT | HOSE | HNX |
|---|---|---|
| 09:00-09:15 | ATO opening auction (board lots + odd-lot LO) | continuous matching (no ATO) |
| 09:15-11:30 | continuous: LO, MTL | continuous: LO, MTL, MOK, MAK |
| 11:30-13:00 | lunch break | lunch break |
| 13:00-14:30 | continuous | continuous |
| 14:30-14:45 | ATC closing auction (+ odd-lot LO) | ATC closing auction |
| 14:45-15:00 | after-hours put-through only | PLO: matching at the closing price |
| put-through | 09:00-11:30 and 13:00-15:00 | 09:00-11:30 and 13:00-15:00 |

What the HNX differences mean for parsing ⚠️ (v1 01 §2, L43):

- **HNX has no opening auction.** HNX `open` is the first continuous match, so an opening gap needs exchange-specific logic.
- **HNX PLO adds volume after the close price is fixed.** A 14:45 snapshot misses it. PLO only runs if ATC set a closing price.
- **The market is fully closed at 15:00** (end of HNX PLO and put-through). ⚠️ (v1 03 §5, L284) The end-of-day cutoff is one config value. Derive it from 15:00 plus a **measured** publication lag of the source. v1 observed the index EOD API lagging 1-2 h and needing a fallback. ❓ v1 observation (v1 03 §5, L284; v1 also states 15:15 and 15:30)
- **Put-through has two phases** (in-hours until 14:45, after-hours 14:45-15:00); tag each print with a phase. ⚠️ (v1 01 §1, L26)
- **Restricted stocks** (trading-restricted list) match by 15-minute periodic auctions all day, so their intraday bars have a different shape; flag them. ⚠️ (v1 01 §1, L27)

Separate volumes at ingest ⚠️ (v1 03 §3.2, L133; v1 04 L1; v1 09 L32, L213 #7):

- `match_qty` (board-lot matching) is the volume for indicators and liquidity.
- Put-through (`put_through`) is a negotiated block, often foreign; mixing it in creates fake volume spikes. Put-through value is **not** counted in VN-Index/HNX-Index. ⚠️ (v1 kpi §A, L16)
- Odd lots (`odd_lot`) trade in auctions too since KRX; keep them apart from board-lot liquidity. ⚠️ (v1 01 L25)

## 3. Price bands and the ceiling/floor formula

⚠️ (v1 01 §3, L54 and v1.2, L75; v1 yml L33)

| Case | HOSE | HNX | UPCoM (reference only) |
|---|---|---|---|
| Normal day (stocks, closed-end funds, ETFs) | ±7% | ±10% | ±15% |
| First trading day of a new listing | ±20% | ±30% | ±40% |
| Resumed after suspension ≥25 days | ±20% *(Medium)* | ±30% *(Medium)* | ±40% |
| Ex-date of stock dividend / bonus shares | ±20% *(Medium)* | ±30% *(Medium)* | ±40% ❓ |
| Ex-date of a rights offer to existing holders | ±7% (no widening) *(Medium)* | ❓ | ❓ |

```
ceiling_price_vnd = round_to_tick(reference_price_vnd × (1 + price_band))
floor_price_vnd   = round_to_tick(reference_price_vnd × (1 − price_band))
if floor_price_vnd < one tick: floor_price_vnd = one tick
```
⚠️ (v1 01 §3, L66). The rounding direction is ❓ (§13). **Take `reference_price_vnd`, `ceiling_price_vnd` and `floor_price_vnd` from the VPS feed**; use the formula only to test the feed. Ceiling/floor values derived from adjusted prices are not valid (v1 had no raw prices).

- Detect corporate actions from the corporate-action calendar, not from `|return| > band`: ex-dates of stock dividends and first listing days run on ±20/30%. ⚠️ (v1 01 L64; v1 09 L213 #12)
- Worst case for a position that cannot be sold before T+2: two limit-down sessions ≈ −14% (HOSE), −20% (HNX). ⚠️ (v1 09 L32)
- With raw intraday prices from the feed, two checks v1 could never run become possible: `price BETWEEN floor AND ceiling` and `price % tick_size = 0` for matched trades. ⚠️ (v1 03 §6.2 #1-2, L508)

## 4. Tick size and lots

⚠️ (v1 01 §4, L103; v1 yml L54, L71)

| Price (VND) | HOSE stock | HNX stock | UPCoM |
|---|---|---|---|
| < 10,000 | 10 | 100 | 100 |
| 10,000 - 49,950 | 50 | 100 | 100 |
| ≥ 50,000 | 100 | 100 | 100 |
| ETF / covered warrant | 10 (all levels) | ❓ | - |
| put-through | 1 | 1 | 1 |

- Prices are tick multiples, so store them as integer VND; equality tests such as `close = ceiling` then stay exact. ⚠️ (v1 03 §3.2, L133)

| Lot rule | HOSE | HNX |
|---|---|---|
| Board lot | 100 shares | 100 shares |
| Odd lot | 1-99 shares | 1-99 shares |
| Max quantity per order | 500,000 | ❓ (often quoted 1,000,000) |
| Min put-through quantity | 20,000 | 5,000 |

Put-through prices must lie within the day's band. ⚠️ (v1 kpi §A, L16)

## 5. Order types after KRX (2025-05-05)

⚠️ (v1 01 §5, L146; v1 yml L82, L98)

| Type | HOSE | HNX | Meaning |
|---|---|---|---|
| LO | ✓ | ✓ | Limit, valid for the day; the only type for odd lots in auctions |
| ATO | ✓ 09:00-09:15 | - | Match at the opening price; remainder cancelled |
| ATC | ✓ 14:30-14:45 | ✓ | Match at the closing price; remainder cancelled |
| MP | removed 2025-05-05 | - | Replaced by MTL; history before that date still has MP |
| MTL | ✓ continuous only | ✓ | Best price; remainder becomes LO one tick beyond the last match |
| MOK | - | ✓ | Fill-or-kill |
| MAK | - | ✓ | Immediate-or-cancel |
| PLO | - | ✓ 14:45-15:00 | Match at the closing price; cannot be amended or cancelled |

- **ATO/ATC no longer have priority over LO** since KRX, so auction matching before and after 2025-05-05 is not comparable. ⚠️ (v1 01 L23; v1 kpi L16)
- Version the `order_type` value set by date (`effective_from`). ⚠️ (v1 01 L22)
- Amending: price and quantity in separate operations; raising price or quantity loses time priority, reducing quantity keeps it; put-through orders cannot be amended, only cancelled and re-entered. ⚠️ (v1 01 L159)
- Matching priority: better price, then earlier time. Auctions pick the price with the largest matched volume, then the one closest to the reference. ⚠️ (v1 01 L161)
- Not live: day trading (T0) and short selling, expected 2027-2028; central counterparty (CCP), target early 2027. ⚠️ re-check (v1 01 §1, L8; v1 yml L89)

## 6. Settlement T+2

⚠️ (v1 01 §6, L165; v1 yml L10)

| When | Event |
|---|---|
| T | Buy matched; cash blocked; shares not yet delivered |
| T+1 | Clearing |
| T+2, 11:00-11:30 (extendable to 12:00) | VSDC and banks settle cash and securities |
| T+2, from 13:00 | Shares sellable, cash withdrawable |

- T+2 since 2022-08-29; the market calls it "T+1.5". The lag counts **trading sessions**, not calendar days. ⚠️
- No T0 strategy exists on the cash market. ⚠️ (v1 09 L213 #6)
- HNX put-through ≥100,000 shares or ≥10 bn VND settles T+1. *(Medium)* ⚠️
- A shorter cycle is now under study with no timeline (§1.1); "no T+1 roadmap" was v1's 2026-08 statement. ⚠️

## 7. Ex-rights adjustment

⚠️ (v1 01 §7, L193; v1 03 §3.3-3.4, L139)

- `ex_rights_date` is the first session a buyer no longer gets the right. Under T+2: `ex_rights_date = record_date − 1 trading session`.
- Reference price on the ex-date:

```
                      P_before + I × P_I − D
reference_price_vnd = ──────────────────────
                          1 + I + B
```

| Symbol | Meaning | Unit |
|---|---|---|
| `P_before` | Close of the session before the ex-date | VND |
| `D` | Cash dividend | VND per share |
| `I` | Paid rights ratio (new shares / old) | ratio |
| `P_I` | Rights subscription price | VND |
| `B` | Bonus shares + stock dividend + split ratio (new / old) | ratio |

Special cases: cash `P − D`; stock dividend or bonus `P / (1 + B)`; split 1:n `P / n`; rights `(P + I × P_I) / (1 + I)`. Worked example (arithmetic checked in code on v1): 40,000; D = 500; B = 0.1; I = 1; P_I = 10,000 → (40,000 + 10,000 − 500) / 2.1 = 23,571.43 before tick rounding.

What to do:

1. **Convert dividends quoted in % of par.** Par value is fixed at 10,000 VND (`par_value_vnd`); "5% dividend" = 500 VND per share, not 5% of price. This is the most common error in Vietnamese adjusted series. ⚠️ (v1 01 L230; v1 06 §1.1, L11; v1 09 #3) The same conversion applies to issue ratios quoted against par.
2. **Round to the exchange's tick** before applying the band. The official rounding rule is ❓, so use the exchange's published reference price (from the feed) and compute only to backfill or cross-check. ⚠️ (v1 01 L233-235)
3. **Expect a widened band** on stock-dividend ex-dates (§3).
4. **Stock dividends, bonus shares and splits create no value**; the price adjusts by the same ratio. Treat them as neutral events. ⚠️ (v1 09 #2; v1 `sentiment_lexicon_vi.yml` `neutral_trap`, L55)

The back-adjustment factor and the price×volume check belong to `indicators.md` (written in K0.3). v1 never validated any adjustment (no raw prices); nothing here claims otherwise (v1 never had raw prices).

## 8. Trading calendar and holidays

**Rule:** trading days = weekdays − exchange holidays. Store it as a calendar table (`is_trading_day`), never compute on the fly. A Saturday make-up workday is **not** a trading day: 2026-08-22 was a civil-service workday with no trading. ⚠️ (v1 01 §8, L257; v1 yml L141)

**History** is inferred from data: a date is a session when **≥ 30 symbols traded**. ⚠️ v1 convention (v1 CLAUDE.md §4 decision 4; v1 03 §6 L363). The threshold is absolute and v1 never re-measured it for the early years (§13).

### 2026 ⚠️ (first 12 rows: HOSE notice, Dec 2025)

| Occasion | Dates | Sessions |
|---|---|---|
| New Year | 01-01 (Thu) | 1 |
| Tết | 02-16 → 02-20 (Mon-Fri) | 5 |
| Hung Kings | 04-27 (Mon) | 1 |
| Reunification + Labour Day | 04-30 → 05-01 (Thu-Fri) | 2 |
| National Day | 08-31 → 09-02 (Mon-Wed) | 3 |
| **Vietnam Culture Day (new)** | **11-24 (Tue)** | **1** |

v1 lists 12 sessions (v1 01 L267). **Vietnam Culture Day is new:** the National Assembly approved 24 November as a paid public holiday (Labour Code total becomes 12 paid holidays a year), first observed Tue 2026-11-24, one day, no day swap. ⚠️ ([Chinhphu.vn](https://xaydungchinhsach.chinhphu.vn/ngay-24-11-hang-nam-la-ngay-van-hoa-viet-nam-nguoi-lao-dong-duoc-nghi-huong-nguyen-luong-119260113152642414.htm), [VnExpress](https://vnexpress.net/khong-hoan-doi-de-keo-dai-ky-nghi-ngay-van-hoa-viet-nam-5127755.html)). **v1's `holidays_2026` (in `02_system/config/market_rules.yml` and its KB mirror) does not contain 2026-11-24.** The exchanges' own closure notice for that day is not verified ❓. Seed it with status `announced` → 13 sessions.

### 2027 - provisional ⚠️

Source: draft of 2026-08-06; Tết 7-day option reportedly approved for public servants. ([Tuổi Trẻ](https://tuoitre.vn/nghi-tet-nguyen-dan-2027-bo-chon-phuong-an-nghi-7-ngay-lien-tuc-100260808092755143.htm), [VnExpress](https://vnexpress.net/du-kien-cac-ngay-nghi-le-tet-nam-2027-5105651.html)) Weekday non-trading dates derived from it:

| Occasion | Weekday dates | Sessions |
|---|---|---|
| New Year | 2027-01-01 (Fri) | 1 |
| Tết (02-04 Thu → 02-10 Wed) | 02-04, 02-05, 02-08, 02-09, 02-10 | 5 |
| Hung Kings | 04-16 (Fri) | 1 |
| 30/4 + 1/5 (1/5 is Sat → compensatory Mon) | 04-30 (Fri), 05-03 (Mon) | 2 |
| National Day | 09-02 (Thu), 09-03 (Fri) | 2 |
| Vietnam Culture Day | 11-24 (Wed) | 1 |

**12 provisional sessions.** Seed them with status `provisional`; replace them with the exchanges' own closure calendar when published (usually December). The private-sector Tết may differ from the public-servant schedule.

### Calendar derivatives

- Weekly bars group by **trading week** (`trading_week_id`), not calendar week: the Tết week has zero sessions and must yield no bar. ⚠️ (v1 04 §9, L525)
- Settlement lags, rolling windows and "previous session" all count `is_trading_day` rows.
- Calendar acceptance tests: 2026 holidays match the seed exactly, and 2026-08-22 is not a session. ⚠️ (v1 10 GĐ0, L45)

## 9. Indices

⚠️ (v1 yml L104; v1 04 §7, L266)

| Index | Members | Method | Weight cap |
|---|---|---|---|
| VN-Index | all HOSE-listed stocks | market cap, base 2000-07-28 = 100 | **none** |
| VN30 | 30 | free-float adjusted | 10% per stock; 40% per GICS-1 sector since 2025-04-16 ⚠️ (v1 kpi L16) |
| VNMID / VN100 / VNAllshare | 70 / 100 / ~286 | free-float adjusted | 10% |
| VNSML | ~186 | free-float adjusted | none |
| HNX-Index | all HNX-listed stocks | market cap, base 2005-07-14 = 100 *(Medium)* | - |
| HNX30 | 30 | free-float adjusted | ❓ |

- **VN-Index is uncapped.** A handful of large caps can lift it while most stocks fall. Show market breadth next to the index. ⚠️ (v1 04 L266; v1 09 #10)
- Review months for the VNAllshare family (VN30, VN100, VNMID, VNSML): **January and July**, with a buffer favouring incumbents. Screens: listed ≥ 6 months, free float > 10%, turnover ≥ 0.05%. ⚠️ (v1 yml L105)
- Whether VN-Index is free-float adjusted is ❓.

## 10. Foreign ownership limits

⚠️ (v1 yml L118; v1 01 §11)

Order of precedence: international treaty → sector law → restricted sector without a stated cap → unrestricted sector; multi-sector companies take the lowest applicable cap.

| Case | Limit (`foreign_ownership_limit_ratio`) |
|---|---|
| Banks, total | 30% |
| Bank: one strategic investor / one institution / one individual | 20% / 15% / 5% |
| Restricted sector without a stated cap | 50% |
| Unrestricted sector | 100% |

- Decree 245/2025 (2025-09-11): companies can no longer set a cap below the legal one; maximum and current room must be published **daily**. ⚠️
- **Since KRX, room is deducted when a buy order is placed**, not when matched. Intraday `foreign_room_remaining_qty` therefore is not ownership; use the end-of-day value for ownership. ⚠️ (v1 01 L24; v1 yml L92)
- Bank room figures are dated; re-verify (dated).

## 11. Regulatory timeline

⚠️ unless noted (v1 01 §1, §11, §13, L382)

| Effective | Change | Data impact |
|---|---|---|
| 2022-08-29 | T+2 settlement | Sellable afternoon of T+2 |
| 2024-11-02 | Circular 68/2024: non-prefunding (NPF) for foreign institutions | - |
| 2025-01-01 | Securities Law amendment 56/2024/QH15 (manipulation, disclosure) | - |
| 2025-05-05 | KRX trading system | §2, §5, §10 changes |
| 2025-09-11 | Decree 245/2025 | Daily foreign-room publication |
| 2026-01-09 | Decree 306/2025: higher penalties | - |
| 2026-02-03 | Circular 08/2026: "global securities company"; tiered NPF sanctions; public NPF-failure disclosure removed | That event source no longer exists |
| 2026-09-21 | FTSE: Frontier → Secondary Emerging, first tranche | Past date; confirm it took effect. Tranche schedule conflicts (§13) |
| 2026-11-24 | First Vietnam Culture Day holiday | §8 |
| 2026-12-28 | HNX stocks trade on HOSE (announced) | §1.1 |
| early 2027 | CCP target | Re-check |
| 2027-2028 | T0 and short selling expected | Re-check |

MSCI: not on the watch list at the 2026-06 review. ⚠️ dated. v1 concluded that 2025-2026 brought no change to hours, bands, ticks, lots or T+2 beyond KRX (v1 01 L395). That held at 2026-08-03. The consolidation changes exchange membership; the items under study could change hours, bands and settlement.

## 12. Seeds derived from this file

v1 kept every rule in one `market_rules.yml` with a single file-level `as_of` (2026-08-03) and no per-rule dates (v1 yml L5). v2 splits it into dbt seeds. Every row carries `effective_from`, `effective_to` (null = open), `as_of` and a source reference; history before the first known date uses `effective_from` = null and the row is tagged ❓.

| Seed | Grain | Content |
|---|---|---|
| `tick_size` | exchange × instrument class × price floor × effective_from | HOSE stock 10/50/100 at 0/10,000/50,000; HNX and UPCoM 100; HOSE ETF/CW 10; put-through 1 |
| `price_band` | exchange × band case × effective_from | §3 table; cases `normal`, `first_trading_day`, `resume_after_25d`, `ex_stock_dividend` |
| `sessions` | exchange × phase × effective_from | §2 table, ICT clock times; pre-KRX rows (with MP, ATO priority) get `effective_to = 2025-05-04` once sourced |
| `holidays` | date (× exchange) | 2026 list (13 dates, 11-24 `announced`); 2027 list (12 dates, `provisional`); status ∈ `announced`, `provisional`, `confirmed` |
| `exchange_alias` | source spelling | `HSX`→HOSE, `HOSE`, `HNX`, `UPCOM`/`UPCoM`→UPCOM, `DELISTED`→null; in-scope flag HOSE, HNX; UPCOM = reference |
| `exchange_changes` | from exchange × effective_from | announced market-wide moves: HNX→HOSE on 2026-12-28 (§1.1). Per-symbol moves still come from the symbol-list snapshots |
| `known_bad_dates` | date | dates whose price rows are dropped as a whole (2018-07-23, carried from v1, cause not recorded ❓) |

Smaller constants (board lot 100, odd lot 1-99, max order HOSE 500,000, put-through minimums, settlement lag 2 sessions, sellable from 13:00, par value 10,000 VND) go in one `market_constants` seed with the same date columns. Per-symbol exchange history is a snapshot model; a market-wide move announced in advance (§1.1) is a seed row, so it applies from its effective date rather than from the day a snapshot notices it. Keep ❓ facts out of the seeds as nulls with a ❓ note, never as values.

Seed tests: a seed fails when `as_of` is older than one quarter, or when next year's holidays are missing after 1 December.

## 13. Open questions (❓)

| # | Question | Effect if wrong |
|---|---|---|
| 1 | Is VN-Index free-float adjusted? (v1 01 L297) | Index contribution analysis drifts |
| 2 | How HOSE rounds the ex-rights reference price (nearest, down, half-even?) (v1 01 L226) | Computed reference prices miss by a tick; use feed values |
| 3 | Rounding direction for ceiling/floor (v1 uses nearest tick) | Same; use feed values |
| 4 | HNX maximum quantity per order (v1 01 L141) | Order-size validation |
| 5 | HNX30 capping and review frequency (v1 yml L113) | Index replication |
| 6 | HNX ETF tick size (v1 10 §2 #8) | Tick-grid test on HNX ETFs |
| 7 | Insider-trading disclosure days before/after a trade (v1 01 §15 #5) | Event timing |
| 8 | UPCoM band on stock-dividend ex-dates (v1 01 §15 #7); bands for rights ex-dates on HNX | Reference only |
| 9 | Consolidation: do moved stocks keep their tickers? | `security_id` mapping |
| 10 | Consolidation: fate of HNX-Index and HNX30; does VN-Index absorb the moved stocks from 2026-12-28? | Index series breaks |
| 11 | Consolidation: are moved stocks on HOSE bands (±7%) and the tiered tick from day one? Presumed yes | `price_band`, `tick_size` |
| 12 | Consolidation: does PLO survive, and do moved stocks gain an ATO? | `sessions` |
| 13 | Exchange closure notice for 2026-11-24 | Calendar |
| 14 | Exchanges' 2027 closure calendar | Calendar |
| 15 | Does "≥ 30 traded symbols" hold for 2000-2006, when HOSE listed fewer than 30 stocks? | Early sessions dropped from the calendar |
| 16 | Index EOD publication lag on the v2 sources (v1 saw 1-2 h) | EOD cutoff |
| 17 | VPS feed field names for reference/ceiling/floor, session phase, put-through and odd lots | Parsing (S0) |
| 18 | FTSE tranche schedule: "3-5 tranches to 2027-09" (v1 01 L334) vs "4 tranches 10/20/35/35%" (v1 kpi L16); did 2026-09-21 take effect? | Event dating only |
| 19 | Restricted-sector default cap: 50% (v1 yml L123) vs "0/30/49/100%" (v1 kpi L16) | `foreign_ownership_limit_ratio` |

Close #1-#8 from the exchanges' rulebooks (PDFs on hose.vn/hnx.vn; the sites are JavaScript apps and need a browser). (v1 01 L461)

## 14. Sources

**v1 KB (private):** `01_market_microstructure.md` §1-§9, §11, §13-§15 · `03_data_architecture_etl.md` §3.2-3.4, §5, §6.2, §7.2 · `04_technical_analysis.md` header, §7, §9 · `06_fundamental_valuation.md` §1.1 · `09_agent_spec.md` §1, §4 · `10_roadmap_backlog.md` GĐ0, §2 · `references/market_rules.yml` · `references/sentiment_lexicon_vi.yml` L55 · `_tham_khao/2026-08-16_kpi_chart_phan_tich_CK_VN.md` §A, Risks · v1 `CLAUDE.md` §4.

**v1's external sources (secondary, ⚠️):** [cafef - KRX go-live](https://cafef.vn/go-live-krx-nhung-thay-doi-quan-trong-co-hieu-luc-ngay-tu-phien-5-5-188250504145303947.chn) · [SSI - KRX FAQ](https://www.ssi.com.vn/khach-hang-ca-nhan/krx-thi-truong-co-so-faq) · [TCBS - HOSE rules](https://help.tcbs.com.vn/quy-dinh-giao-dich-tai-hsx-krx/) · [TCBS - HNX rules](https://help.tcbs.com.vn/quy-dinh-giao-dich-chung-khoan-tai-hnx-krx/) · [Vietstock - T+2](https://vietstock.vn/2022/08/chinh-thuc-rut-ngan-thoi-gian-giao-dich-t15-tu-2908-143-994183.htm) · [Vietstock - HOSE rules](https://vietstock.vn/2021/07/quy-che-giao-dich-moi-tai-hose-duy-tri-bien-do-dao-dong-gia-7-va-lo-chan-100-cp-143-871725.htm) · [APEC - ex-rights reference price](https://apec.com.vn/ho-tro/29-cach-tinh-gia-tham-chieu-cua-chung-khoan-tai-ngay-giao-dich-khong-huong-quyen/) · [Vietstock - 2026 holidays](https://vietstock.vn/2025/12/hose-thong-bao-lich-nghi-giao-dich-nam-2026-830-1379614.htm) · [VnEconomy - FTSE](https://vneconomy.vn/ftse-russell-xac-nhan-viet-nam-vuot-qua-ky-review-chinh-thuc-nang-hang-vao-thang-92026.htm) · [VietnamBiz - MSCI 2026-06](https://vietnambiz.vn/chung-khoan-viet-nam-tiep-tuc-lo-hen-watch-list-cua-msci-202662465834933.htm) · [LSVN - Circular 08/2026](https://lsvn.vn/nhung-diem-moi-cua-thong-tu-08-2026-tt-btc-ve-chung-khoan-giao-dich-co-phieu-a169838.html) · [Tuổi Trẻ - 2026 securities policies](https://tuoitre.vn/loat-chinh-sach-moi-ve-chung-khoan-co-hieu-luc-tu-dau-nam-2026-20260103030158144.htm)

**Researched 2026-10-08 (news, ⚠️):** [VOH - HNX to HOSE](https://voh.com.vn/kinh-te/co-phieu-niem-yet-hnx-se-chuyen-toan-bo-sang-hose-tu-cuoi-thang-122026-671087.html) · [VTV - timing and lunch trading](https://vtv.vn/chuyen-toan-bo-co-phieu-hnx-sang-hose-trong-2026-nghien-cuu-giao-dich-xuyen-trua-100261006194652428.htm) · [KTCK - VNX roadmap, HOSE boards](https://kinhtechungkhoan.vn/vnx-cap-nhat-lo-trinh-sap-xep-lai-thi-truong-co-phieu-diem-nhan-la-phan-bang-tai-hose-1390806.html) · [Chinhphu.vn - Culture Day](https://xaydungchinhsach.chinhphu.vn/ngay-24-11-hang-nam-la-ngay-van-hoa-viet-nam-nguoi-lao-dong-duoc-nghi-huong-nguyen-luong-119260113152642414.htm) · [VnExpress - Culture Day, no swap](https://vnexpress.net/khong-hoan-doi-de-keo-dai-ky-nghi-ngay-van-hoa-viet-nam-5127755.html) · [Tuổi Trẻ - Tết 2027](https://tuoitre.vn/nghi-tet-nguyen-dan-2027-bo-chon-phuong-an-nghi-7-ngay-lien-tuc-100260808092755143.htm) · [VnExpress - 2027 holidays draft](https://vnexpress.net/du-kien-cac-ngay-nghi-le-tet-nam-2027-5105651.html)

New terms used here are defined in [`../../CONTEXT.md`](../../CONTEXT.md).
