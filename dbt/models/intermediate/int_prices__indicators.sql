-- Per symbol and session: return against the reference (the previous session's close)
-- and point-in-time indicators over non-stale sessions (docs/knowledge/indicators.md §2:
-- SMA(n, t) = mean of the last n closes including t; NULL until n non-stale sessions
-- exist). Stale rows (no trade, price copied) get no indicator and never count.
-- 52-week high / low: the close is the highest / lowest of the last `high_low_rows`
-- non-stale closes, once that many exist.
with prices as (
    select
        symbol, trade_date, session_seq, exchange, is_in_scope, is_stale, close_vnd,
        lag(close_vnd) over (partition by symbol order by session_seq) as reference_vnd
    from {{ ref('fct_price_daily') }}
),

traded as (
    select
        symbol,
        trade_date,
        close_vnd,
        count(*) over (partition by symbol order by session_seq rows between unbounded preceding and current row) as traded_rows,
        avg(close_vnd) over (partition by symbol order by session_seq rows between {{ var('ma_short_rows') - 1 }} preceding and current row) as ma_short_raw,
        avg(close_vnd) over (partition by symbol order by session_seq rows between {{ var('ma_medium_rows') - 1 }} preceding and current row) as ma_medium_raw,
        avg(close_vnd) over (partition by symbol order by session_seq rows between {{ var('ma_long_rows') - 1 }} preceding and current row) as ma_long_raw,
        max(close_vnd) over (partition by symbol order by session_seq rows between {{ var('high_low_rows') - 1 }} preceding and current row) as high_window_vnd,
        min(close_vnd) over (partition by symbol order by session_seq rows between {{ var('high_low_rows') - 1 }} preceding and current row) as low_window_vnd
    from prices
    where not is_stale
)

select
    p.symbol,
    p.trade_date,
    p.session_seq,
    p.exchange,
    p.is_in_scope,
    p.is_stale,
    p.close_vnd,
    p.reference_vnd,
    case
        when not p.is_stale and p.reference_vnd > 0
            then p.close_vnd / p.reference_vnd - 1
    end as return_1d_ratio,
    case when t.traded_rows >= {{ var('ma_short_rows') }} then t.ma_short_raw end as ma20_vnd,
    case when t.traded_rows >= {{ var('ma_medium_rows') }} then t.ma_medium_raw end as ma50_vnd,
    case when t.traded_rows >= {{ var('ma_long_rows') }} then t.ma_long_raw end as ma200_vnd,
    case
        when t.traded_rows >= {{ var('high_low_rows') }} then t.close_vnd >= t.high_window_vnd
    end as is_new_high_52w,
    case
        when t.traded_rows >= {{ var('high_low_rows') }} then t.close_vnd <= t.low_window_vnd
    end as is_new_low_52w
from prices as p
left join traded as t
    on t.symbol = p.symbol and t.trade_date = p.trade_date
