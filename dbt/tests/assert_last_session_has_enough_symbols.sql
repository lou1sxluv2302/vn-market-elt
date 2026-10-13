-- v1 dq 21. The newest date in fct_price_daily has at least
-- `min_traded_symbols_per_session` traded symbols; an empty mart fails too.
-- Fails on: a partial pull (a handful of symbols on a new date) kept as the newest session,
-- e.g. when the mart stops cutting rows after the last observed session.
with newest as (
    select max(trade_date) as trade_date from {{ ref('fct_price_daily') }}
)

select n.trade_date, count(distinct case when p.match_qty > 0 then p.symbol end) as traded
from newest as n
left join {{ ref('fct_price_daily') }} as p on p.trade_date = n.trade_date
group by n.trade_date
having count(distinct case when p.match_qty > 0 then p.symbol end)
    < {{ var('min_traded_symbols_per_session') }}
