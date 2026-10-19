# Runbook - the end-of-day BI report (Power BI)

One semantic model, one report, several pages, imported from the `marts_daily` tables
(spec D10; `docs/knowledge/bi-conventions.md`). The intraday views of S3 join the same
model later in DirectQuery (a composite model). Until P5 the project file is kept outside
this repository: its queries carry the project id (§14.8); P5 publishes a copy pointed at
the synthetic warehouse.

## 1. Connect (once, the owner)

1. Install **Power BI Desktop** (Microsoft Store; Windows only).
2. *File → Options and settings → Options → Preview features*: tick *Power BI Project
   (.pbip) save option*, *Store semantic model using TMDL format* and *Store reports using
   enhanced metadata format (PBIR)* where they are listed (unlisted = already default).
   Restart.
3. *Get data → Google BigQuery* (not the Entra ID variant) → *Advanced options*: billing
   project = the project id; keep *Use Storage Api* → *Sign in* with the Google account
   that owns the project. The credential stays in Power BI's per-user store, not in the
   project files.
4. Navigator → the project → **`marts_daily` only** → the tables of §2 → *Load*, mode
   **Import**.
5. *Save as* → *Power BI project files (*.pbip)*.

## 2. Tables

| Table | Grain | Rows (2026-10-19) | Role |
|---|---|---|---|
| `dim_trading_calendar` | calendar day | 8,400 | the date dimension; `session_seq` drives every time axis |
| `dim_trading_period` | period type × id | 1.5 k | week / month / year: `session_count`, `is_period_complete` |
| `dim_security` | symbol × exchange period | 1.8 k | symbol attributes |
| `fct_symbol_session_daily` | symbol × session | 4.6 M | prices, return, MA20/50/200, 52-week flags, liquidity, universe, foreign flow |
| `fct_market_breadth_daily` | exchange × session | 10.6 k | counts; ratios are measures (sum of counts / sum of denominators) |
| `fct_market_flow_daily` | exchange × session | 5.9 k | foreign and proprietary net; split only where valid |
| `fct_universe_summary_daily` | exchange × session | 16 k | universe size, tiers, entries, exits |
| `fct_index_daily` | index × session | 22 k | index levels |
| `fct_build_status` | prod build | 1 per build | `as_of_date` and test outcome for every page's header |

Relationships: one-to-many, single direction, from `dim_trading_calendar[calendar_date]`
to each fact's `trade_date`, and from a symbol dimension to `fct_symbol_session_daily`.
No bi-directional filter.

## 3. Refresh

After the evening build (the daily run after 16:30): *Home → Refresh*. One refresh reads
about 1 GB (the symbol fact dominates); the free tier is 1 TB a month.

## 4. Checks

- Model and pages: `tools/check_pbip.py` (BI plan Q3) on the saved project.
- Numbers: `tools/check_bi_numbers.py --as-of D` against one DAX query run in Desktop's
  DAX query view (BI plan Q2).
