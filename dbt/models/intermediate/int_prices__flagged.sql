-- Quality flags per price row, with v1's definitions so the two can be reconciled exactly.
-- is_stale: no trade and the close copied from the symbol's previous row (over every row of
-- the symbol, flagged or not); null on a symbol's first row. Stale rows are excluded from
-- every calculation downstream. is_open_outside_range is v1's extra drop rule for
-- non-stale rows (bad_ohlc does not look at open). Trading-day membership is checked in
-- the marts, against dim_trading_calendar.
with priced as (
    select
        *,
        lag(close_vnd) over (partition by symbol order by trade_date) as prev_close_vnd
    from {{ ref('int_prices__chosen_source') }}
)

select
    p.*,
    (p.match_qty = 0 and p.close_vnd = p.prev_close_vnd) as is_stale,
    {{ is_bad_null('p.') }} as is_bad_null,
    {{ is_bad_nonpositive('p.') }} as is_bad_nonpositive,
    {{ is_bad_ohlc('p.') }} as is_bad_ohlc,
    (b.bad_date is not null) as is_bad_known_date,
    (p.open_vnd < p.low_vnd or p.open_vnd > p.high_vnd) as is_open_outside_range
from priced as p
left join {{ ref('known_bad_dates') }} as b
    on b.bad_date = p.trade_date
