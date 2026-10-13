# Vietnamese equity market data

The language of vn-market-elt: how HOSE/HNX market concepts are named in prose,
issues, tests and code. The **single source** for terms (ADR-0025). Add a term here
**before** using it anywhere; two names for one concept cannot be reconciled by
any check. Each entry: definition · code name · Vietnamese term · words to avoid.

Definitions only; rules, limits and dates for these terms live in `docs/knowledge/`.

Units everywhere: prices are integer VND (`_vnd`), never thousand VND · timestamps
are UTC (`_at`) · dates are Vietnam time (`_date`). Column suffixes: spec §13.

## Language

### Market structure

**Exchange** (`exchange`) · _sàn giao dịch_:
The venue a security is listed on: `HOSE`, `HNX` or `UPCOM`; time-varying per security.
_Avoid_: market, bourse, `HSX`

**Symbol** (`symbol`) · _mã chứng khoán_:
The ticker a security trades under; it can change.
_Avoid_: ticker, code, stock id

**Security** (`security_id`) · _mã định danh nội bộ_:
One listed instrument, stable across ticker and exchange changes.
_Avoid_: stock, symbol (when the stable identity is meant)

**Index** (`index`, `index_code`) · _chỉ số_:
A published market index such as VN-Index, VN30 or HNX-Index.

**Session** (`session`, `trade_date`) · _phiên giao dịch_:
One trading day, identified by its Vietnam-time date.
_Avoid_: day, bar

**Session phase** (`session_phase`) · _pha phiên_:
A part of the session with its own matching rules: `opening_auction`, `continuous`, `lunch_break`, `closing_auction`, `post_close_auction` (HNX PLO), `put_through`.

**Opening auction / closing auction** (`opening_auction`, `closing_auction`) · _ATO / ATC_:
The call auctions that set the opening and closing price.

**Order type** (`order_type`) · _loại lệnh_:
LO, ATO, ATC, MTL, MOK, MAK or PLO; the valid set is versioned by date.

**Match** (`match`, `match_qty`, `match_value_vnd`) · _khớp lệnh_:
A trade from the order book in board lots. Matched volume is the volume for indicators and liquidity.
_Avoid_: volume (unqualified)

**Put-through** (`put_through`, `put_through_qty`) · _giao dịch thoả thuận_:
A negotiated block trade outside the order book. Kept apart from matched volume.
_Avoid_: deal, block

**Total quantity** (`total_qty`) · _tổng khối lượng_:
Matched plus put-through quantity. Prefixes `match_` · `put_through_` · `total_` split every volume and value.

**Board lot / odd lot** (`board_lot`, `odd_lot`) · _lô chẵn / lô lẻ_:
A multiple of 100 shares / an order of 1-99 shares.

**Price board / order book** (`price_board`, `order_book`) · _bảng giá / sổ lệnh_:
The live quote screen / the queue of resting orders.

**Covered warrant** (`covered_warrant`) · _chứng quyền_:
A warrant issued by a securities firm on an underlying stock.

**Trading-restricted** (`is_trading_restricted`) · _bị hạn chế giao dịch_:
A security that trades only in periodic auctions.

### Prices and limits

**Reference price** (`reference_price_vnd`) · _giá tham chiếu_:
The exchange's base price for the session; intraday change is measured from it.
_Avoid_: previous close, yesterday's close

**Ceiling price / floor price** (`ceiling_price_vnd`, `floor_price_vnd`) · _giá trần / giá sàn_:
The highest and lowest price allowed in the session.

**Price band** (`price_band`) · _biên độ dao động_:
The allowed move from the reference price, set per exchange and case.
_Avoid_: limit, range

**Tick size** (`tick_size`) · _bước giá_:
The smallest price increment for a security at a given price and date.

**Limit-locked** (`is_limit_locked`) · _khoá trần / sàn_:
A session where the price sits at the ceiling or floor with no match possible on one side.

**Raw price / adjusted price** (`raw_price`, `adjusted_price`) · _giá thô / giá điều chỉnh_:
The price actually traded / a history rewritten by the vendor after corporate actions.
_Avoid_: close (unqualified)

**Par value** (`par_value_vnd`) · _mệnh giá_:
10,000 VND; dividends and issue ratios are quoted as a percentage of it.

### Corporate actions

**Corporate action** (`corporate_action`) · _sự kiện quyền_:
A dividend, bonus issue, split or rights issue that changes price or share count.

**Ex-rights date** (`ex_rights_date`) · _GDKHQ, ngày giao dịch không hưởng quyền_:
The first session in which a buyer no longer receives the right.
_Avoid_: ex-date (unqualified), record date

**Record date** (`record_date`) · _ngày đăng ký cuối cùng_:
The date that fixes who receives the right.

**Cash dividend** (`cash_dividend_vnd`) · _cổ tức tiền mặt_:
A per-share cash payment, converted from its percentage of par value.

### Ownership and flows

**Foreign flow** (`foreign_flow`, `foreign_buy_value_vnd`, `foreign_sell_value_vnd`) · _khối ngoại_:
Trading by foreign investors.

**Foreign ownership limit** (`foreign_ownership_limit_ratio`) · _giới hạn sở hữu nước ngoài_:
The maximum share of a company foreigners may own.
_Avoid_: room (for the limit itself)

**Foreign room remaining** (`foreign_room_remaining_qty`) · _room khối ngoại còn lại_:
Shares foreigners may still buy.

**Proprietary trading** (`proprietary_trading`, prefix `prop_`) · _tự doanh_:
Trading by securities firms on their own account.

**Foreign net flow** (`foreign_net_match_value_vnd`) · _khối ngoại mua/bán ròng khớp lệnh_:
Foreign matched buy value minus foreign matched sell value in a session.
_Avoid_: net foreign (unqualified), foreign net total

**Foreign pressure** (`foreign_pressure`; `prop_pressure` for proprietary trading) · _áp lực khối ngoại_:
Foreign matched net value divided by the session's matched value.
_Avoid_: foreign ratio, flow strength

**Foreign intensity** (`foreign_intensity`) · _mức tham gia của khối ngoại_:
Foreign matched buy plus sell value divided by the session's matched value.
_Avoid_: foreign share, participation (unqualified)

**Foreign ownership share** (`foreign_own_pct`, `room_used_pct`) · _tỷ lệ sở hữu nước ngoài / room đã dùng_:
End-of-day foreign holding over point-in-time shares outstanding, and that share over the foreign ownership limit.
_Avoid_: room (for the share held)

**Breakdown validity** (`is_breakdown_valid`) · _tách khớp/thoả thuận hợp lệ_:
Whether match + put-through equals total for a row; when false the split columns are NULL and total is kept.
_Avoid_: clean, verified

**Domestic institution** (`domestic_institution`) · _tổ chức trong nước_:
A Vietnamese institutional investor.

**Insider deal** (`insider_deal`) · _giao dịch nội bộ_:
A trade by an insider or related party, disclosed with a publication date.

**Index contribution** (`index_contribution`) · _đóng góp điểm số_:
A symbol's price change times its point-in-time shares; its share of the absolute total measures point concentration.
_Avoid_: weight, impact, pillar pull

**Index event day** (`is_index_event_day`) · _ngày cơ cấu rổ_:
A session when index reviews or provider changes take effect, so foreign flow is mechanical.
_Avoid_: rebalance (unqualified), ETF day

**Market breadth** (`market_breadth`) · _độ rộng thị trường_:
Counts of advancing, declining, unchanged, ceiling and floor securities in a session.

**Active symbol count** (`active_symbol_count`) · _số mã hoạt động trong phiên_:
Securities that traded in the session; the denominator of most breadth ratios (`pct_advancing` divides by advancing + declining).

**Advance/decline** (`advancing_count`, `declining_count`, `pct_advancing`) · _mã tăng / mã giảm_:
Symbols closing above / below the reference price; `pct_advancing` excludes unchanged symbols.
_Avoid_: gainers/losers, breadth % (unqualified)

**Ceiling/floor spread** (`ceiling_floor_spread_ratio`) · _chênh lệch trần/sàn_:
Ceiling count minus floor count over the active symbol count, from the feed's ceiling and floor prices.
_Avoid_: ceiling/floor count as a threshold

### Liquidity and universe

**Liquidity** (`liquidity`, `adv_20d_vnd`) · _thanh khoản_:
Traded value; ADV is the 20-session average daily value, excluding the current session.

**Stale session** (`is_stale`) · _phiên đứng giá_:
A session with zero volume and a copied price; excluded from every calculation.
_Avoid_: missing session, holiday

**Universe** (`is_in_universe`) · _universe tại thời điểm_:
The securities eligible on a given session, decided only from earlier data.
_Avoid_: watchlist, today's top N

**Listing status** (`listing_status`, `delisted_date`) · _trạng thái niêm yết_:
Listed or delisted; delisted securities stay in history.

### Indicators

**Moving average** (`sma_<n>`, `ema_<n>`) · _đường trung bình_:
SMA is the plain mean of the last n session closes; EMA is recursive with weight 2/(n+1), updated per session and provisionally intraday.
_Avoid_: MA (unqualified)

**Warm-up** (`is_warmup`) · _giai đoạn khởi động_:
The leading sessions in which an indicator lacks its required inputs and is NULL.
_Avoid_: burn-in (the convergence span used to compare implementations)

**Volume ratio** (`volume_ratio`) · _tỷ lệ khối lượng_:
A session's matched quantity over its 20-session average matched quantity.
_Avoid_: relative volume, volume spike

**VWAP** (`vwap_vnd`) · _giá bình quân gia quyền khối lượng_:
Matched value over matched quantity, from trade-level data.
_Avoid_: average price

**Cumulative adjustment factor** (`cum_adj_factor`, per event `adj_factor`) · _hệ số điều chỉnh tích luỹ_:
The product of the adjustment factors of all corporate actions after a date; adjusted price = raw price × it.
_Avoid_: split factor, back-adjustment ratio

**Rounding toward safety** (rule, no column) · _làm tròn về phía an toàn_:
Rounding a derived price level onto the tick grid in the direction that makes the computed risk larger.
_Avoid_: round to nearest (for order levels)

### Calendar

**Trading day** (`is_trading_day`) · _ngày giao dịch_:
A weekday that is not an exchange holiday. A make-up Saturday is not one.

**Holiday status** (`holiday_status`) · _trạng thái ngày nghỉ_:
`announced` or `provisional` for each exchange holiday.

**Session sequence** (`session_seq`) · _số thứ tự phiên_:
A gap-free integer over trading days; the key for "N sessions ago".

**Trading week** (`trading_week_id`) · _khoá tuần giao dịch_:
A week built from trading days, not calendar weeks.

**Session count** (`session_count`, `is_period_complete`) · _số phiên trong kỳ_:
The number of sessions in a period, and whether the period has ended; mandatory on every period aggregate.

**Trading period keys** (`trading_month_id`, `trading_year_id`) · _khoá kỳ giao dịch_:
Month and year keys built from trading sessions, recomputed whenever the session set changes.
_Avoid_: calendar month

**Month-end session** (`is_month_end_session`, `is_quarter_end_session`) · _phiên cuối tháng / quý_:
The last trading session of a month or quarter, not its last calendar day.
_Avoid_: EOM date

### Disclosure and fundamentals

**Available-from date** (`available_from_date`) · _ngày công bố khả dụng_:
The first date a disclosed figure may be used; joins use it, never the period end.

**Period end date** (`period_end_date`) · _ngày kết thúc kỳ_:
The last day of a reporting period.

**Publication lag** (`publication_lag_days`) · _độ trễ công bố_:
Days from period end to availability.

**Shares outstanding** (`shares_outstanding`, `is_shares_pit`) · _số cổ phiếu lưu hành_:
Shares in issue as of a date; today's count applied to the past is look-ahead.

**Market capitalisation** (`market_cap_vnd`) · _vốn hoá_:
Own close × point-in-time shares outstanding; never the vendor's figure.

**Charter capital** (`charter_capital_vnd`) · _vốn điều lệ_:
Registered capital.

**Trailing twelve months** (suffix `_ttm`) · _luỹ kế 4 quý_:
The sum of the last four published quarters.

### Data model

**Effective period** (`effective_from`, `effective_to`) · _hiệu lực từ / đến_:
The validity window of a seed row or a dimension version; `effective_to` is exclusive and NULL means open.

**Source role** (`source_role`) · _vai nguồn_:
`primary`, `fallback` or `verifier`; exactly one primary per dataset.

**Aggregation suffix** (`_sum`, `_avg`, `_close`) · _hậu tố luật gộp_:
The suffix stating how a metric aggregates over a period; one rule per metric.
_Avoid_: reusing the daily column name for a period value

### Reporting

**As-of** (`as_of`) · _mốc dữ liệu_:
The latest session or timestamp a visual is built from; shown on every page, one per page.
_Avoid_: last updated, refresh time

**Colour role** (`colour_up`, `colour_down`, `colour_ceiling`, `colour_floor`, `colour_reference`) · _màu tăng / giảm / trần / sàn / tham chiếu_:
A named meaning a colour carries; values live in `config/palette.yml`.
_Avoid_: green, red (as names)

**Secondary encoding** (`secondary_encoding`) · _mã hoá phụ_:
A non-colour channel (▲▼ glyph, signed number, edge mark) carrying the same meaning as a colour.
_Avoid_: decoration, icon

**Diverging heat scale** (`diverging_scale`) · _thang nhiệt phân cực_:
Two hues for sign, two lightness steps each, a neutral midpoint.
_Avoid_: traffic light, red-yellow-green
