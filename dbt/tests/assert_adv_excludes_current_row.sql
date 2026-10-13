-- No look-ahead in ADV: a symbol's first non-stale row has no previous row to read, so its
-- window is empty. Fails on: a window that includes the current row, which a row-count
-- limit alone misses when the window is also shortened by one (`19 preceding and current row`).
with firsts as (
    select symbol, min(session_seq) as first_seq
    from {{ ref('fct_liquidity_daily') }}
    group by symbol
)

select l.symbol, l.trade_date, l.adv_rows
from {{ ref('fct_liquidity_daily') }} as l
join firsts as f on f.symbol = l.symbol and f.first_seq = l.session_seq
where l.adv_rows <> 0
