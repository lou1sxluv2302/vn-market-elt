-- Clean daily prices, one row per (symbol, trade_date), with v1's drop rules:
-- bad null / non-positive / OHLC / known bad date, not a trading day, a non-stale row
-- with its open outside [low, high] (three-valued, as v1: a null-stale row with a bad
-- open is dropped too), and anything after the last observed session. Stale rows stay,
-- with open = high = low = close. Exchange, tick and band are those of the trade date.
with calendar as (
    select * from {{ ref('dim_trading_calendar') }}
),

last_observed as (
    select max(calendar_date) as last_session
    from calendar
    where calendar_source = 'observed' and is_trading_day
),

kept as (
    select p.*, c.session_seq, c.trading_week_id
    from {{ ref('int_prices__flagged') }} as p
    join calendar as c on c.calendar_date = p.trade_date and c.is_trading_day
    cross join last_observed as lo
    where not p.is_bad_null
        and not p.is_bad_nonpositive
        and not p.is_bad_ohlc
        and not p.is_bad_known_date
        and not (p.is_stale = false and p.is_open_outside_range)
        and p.trade_date <= lo.last_session
),

with_exchange as (
    select k.*, s.exchange, s.is_in_scope, s.exchange_is_inferred
    from kept as k
    left join {{ ref('dim_security') }} as s
        on s.symbol = k.symbol
        and (s.effective_from is null or k.trade_date >= s.effective_from)
        and (s.effective_to is null or k.trade_date < s.effective_to)
),

with_tick as (
    select
        w.*,
        t.tick_vnd,
        row_number() over (
            partition by w.symbol, w.trade_date order by t.price_from_vnd desc
        ) as tick_rank
    from with_exchange as w
    left join {{ ref('tick_size') }} as t
        on t.exchange = w.exchange
        and t.instrument_class = 'stock'
        and t.price_from_vnd <= w.close_vnd
        and (t.effective_from is null or w.trade_date >= t.effective_from)
        and (t.effective_to is null or w.trade_date < t.effective_to)
)

select
    w.symbol,
    w.trade_date,
    w.session_seq,
    w.trading_week_id,
    w.exchange,
    w.is_in_scope,
    w.exchange_is_inferred,
    case when w.is_stale then w.close_vnd else w.open_vnd end as open_vnd,
    case when w.is_stale then w.close_vnd else w.high_vnd end as high_vnd,
    case when w.is_stale then w.close_vnd else w.low_vnd end as low_vnd,
    w.close_vnd,
    w.match_qty,
    w.close_vnd * w.match_qty as turnover_vnd,
    w.is_stale,
    w.tick_vnd,
    b.band_ratio as price_band_ratio,
    w._source_id
from with_tick as w
left join {{ ref('price_band') }} as b
    on b.exchange = w.exchange
    and b.band_case = 'normal'
    and (b.effective_from is null or w.trade_date >= b.effective_from)
    and (b.effective_to is null or w.trade_date < b.effective_to)
where w.tick_rank = 1
