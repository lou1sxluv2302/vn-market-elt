-- v1 dq 21b/21c, point in time. A price row's exchange is dim_security's for the period
-- holding its date. Fails on: the mart taking a symbol's current exchange for every date,
-- which puts an HNX stock on HOSE before the market-wide move.
select p.symbol, p.trade_date, p.exchange, s.exchange as period_exchange
from {{ ref('fct_price_daily') }} as p
join {{ ref('dim_security') }} as s
    on s.symbol = p.symbol
    and (s.effective_from is null or p.trade_date >= s.effective_from)
    and (s.effective_to is null or p.trade_date < s.effective_to)
where p.exchange is distinct from s.exchange
