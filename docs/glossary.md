# Glossary — Vietnamese market terms

The **single source** for how Vietnamese market concepts are named in code
(spec D15). Add a term here **before** using it in code. Two English names for
one concept cannot be reconciled by any check.

| Vietnamese | Code name | Notes |
|---|---|---|
| phiên giao dịch | `session` · `trade_date` | `trade_date` is a DATE in Vietnam time |
| giá tham chiếu | `reference_price_vnd` | The base for intraday % change — never the adjusted close |
| giá trần / giá sàn | `ceiling_price_vnd` / `floor_price_vnd` | |
| biên độ dao động | `price_band` | HOSE ±7%, HNX ±10%, UPCoM ±15% |
| bước giá | `tick_size` | |
| GDKHQ — ngày giao dịch không hưởng quyền | `ex_rights_date` | |
| sự kiện quyền | `corporate_action` | Dividends, splits, rights issues |
| giá điều chỉnh / giá thô | `adjusted_price` / `raw_price` | Vendors rewrite adjusted history after corporate actions |
| khối ngoại | `foreign_flow` · `foreign_buy_value_vnd` · `foreign_sell_value_vnd` | |
| tự doanh (công ty chứng khoán) | `proprietary_trading` · prefix `prop_` | |
| giao dịch thoả thuận | `put_through` | |
| lô lẻ | `odd_lot` | |
| độ rộng thị trường | `market_breadth` | Advancing / declining / unchanged / ceiling / floor counts |
| thanh khoản | `liquidity` · `adv_20d_vnd` | ADV = average daily traded value |
| phiên «đứng giá» (khối lượng = 0) | `is_stale` | Excluded from every calculation |
| mã chứng khoán | `symbol` | |
| sàn giao dịch (HOSE / HNX / UPCoM) | `exchange` | |
| ATO / ATC | `opening_auction` / `closing_auction` | |
| khớp lệnh | `match` · `match_qty` · `match_value_vnd` | |
| chỉ số (VN-Index, VN30, HNX-Index) | `index` · `index_code` | |

Units: prices are **integer VND** (`_vnd`), never "thousand VND". Timestamps
are **UTC** (`_at`); dates are **Vietnam time** (`_date`).

## Data-model terms

Added 2026-10-08 from the K0.2 knowledge files. Same rule: add here first.

| Concept (Vietnamese) | Code name | Notes |
|---|---|---|
| mã định danh nội bộ của chứng khoán | `security_id` | Stable across ticker or exchange changes; `symbol` is the ticker |
| hiệu lực từ / đến | `effective_from` / `effective_to` | Seeds and SCD2 dimensions; `effective_to` is exclusive, NULL = open |
| ngày giao dịch | `is_trading_day` | In the calendar dimension |
| trạng thái ngày nghỉ | `holiday_status` | `announced` · `provisional` |
| số thứ tự phiên | `session_seq` | Gap-free integer over trading days; the key for "N sessions ago" |
| khoá tuần giao dịch | `trading_week_id` | Built from trading days, not calendar weeks |
| số phiên trong kỳ · kỳ đã đủ | `session_count` · `is_period_complete` | Mandatory on every period aggregate |
| pha phiên | `session_phase` | `opening_auction` · `continuous` · `lunch_break` · `closing_auction` · `post_close_auction` (HNX PLO) · `put_through` |
| loại lệnh | `order_type` | |
| lô chẵn | `board_lot` | 100 shares |
| mệnh giá | `par_value_vnd` | 10,000 VND |
| ngày đăng ký cuối cùng | `record_date` | |
| cổ tức tiền mặt | `cash_dividend_vnd` | Per share, from % of par |
| giới hạn sở hữu nước ngoài | `foreign_ownership_limit_ratio` | Maximum allowed foreign ownership |
| room khối ngoại còn lại | `foreign_room_remaining_qty` | Shares foreigners may still buy |
| bị hạn chế giao dịch | `is_trading_restricted` | |
| tổng khối lượng (khớp + thoả thuận) | `total_qty` | Prefixes `match_` · `put_through_` · `total_` split volume and value: `match_qty`, `put_through_qty`, `total_qty` |
| khoá trần / sàn | `is_limit_locked` | Requires real ceiling/floor prices (from the feed) |
| universe tại thời điểm | `is_in_universe` | Point-in-time, per session |
| số mã hoạt động trong phiên | `active_symbol_count` | The denominator of breadth ratios |
| trạng thái niêm yết · ngày huỷ niêm yết | `listing_status` · `delisted_date` | |
| vai nguồn | `source_role` | `primary` · `fallback` · `verifier` |
| ngày công bố khả dụng · ngày kết thúc kỳ | `available_from_date` · `period_end_date` | Join financial data on `available_from_date`, never on the period end |
| độ trễ công bố | `publication_lag_days` | |
| số cổ phiếu lưu hành | `shares_outstanding` · `is_shares_pit` | Today's share count applied to the past is look-ahead |
| vốn hoá | `market_cap_vnd` | Recomputed from own price × point-in-time shares |
| vốn điều lệ | `charter_capital_vnd` | |
| bảng giá · sổ lệnh | `price_board` · `order_book` | |
| chứng quyền | `covered_warrant` | |
| giao dịch nội bộ | `insider_deal` | |
| tổ chức trong nước | `domestic_institution` | |
| luỹ kế 4 quý | suffix `_ttm` | Trailing twelve months, last four **published** quarters |
