-- BI plan B1. MA20 recomputed from the last `ma_short_rows` non-stale closes up to and
-- including the session (indicators.md §2), for the last `bi_check_sessions` sessions, by a
-- self-join on per-symbol row numbers instead of a window. Fails on: a window that reaches
-- forward (look-ahead), one that counts stale rows, or a mean shown during warm-up.
with traded as (
    select
        symbol, trade_date, session_seq, close_vnd,
        row_number() over (partition by symbol order by session_seq) as traded_rn
    from {{ ref('fct_price_daily') }}
    where not is_stale
),

checked as (
    select t.symbol, t.trade_date, t.traded_rn
    from traded as t
    where t.session_seq > (
        select max(session_seq) - {{ var('bi_check_sessions') }} from {{ ref('fct_price_daily') }}
    )
),

recomputed as (
    select
        c.symbol,
        c.trade_date,
        case
            when c.traded_rn >= {{ var('ma_short_rows') }} then avg(h.close_vnd)
        end as ma20_expected
    from checked as c
    join traded as h
        on h.symbol = c.symbol
        and h.traded_rn between c.traded_rn - {{ var('ma_short_rows') }} + 1 and c.traded_rn
    group by c.symbol, c.trade_date, c.traded_rn
)

select i.symbol, i.trade_date, i.ma20_vnd, r.ma20_expected
from recomputed as r
join {{ ref('int_prices__indicators') }} as i
    on i.symbol = r.symbol and i.trade_date = r.trade_date
where (i.ma20_vnd is null) != (r.ma20_expected is null)
    or abs(i.ma20_vnd - r.ma20_expected) > 0.001
