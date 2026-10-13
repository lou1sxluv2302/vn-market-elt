-- v1 dq 15. No stale (or null-stale) row is in the universe.
-- Fails on: stale rows reaching the universe, which takes both guards gone: the liquidity
-- mart reading stale rows and the universe not excluding them.
select u.symbol, u.trade_date
from {{ ref('fct_universe_daily') }} as u
join {{ ref('fct_price_daily') }} as p on p.symbol = u.symbol and p.trade_date = u.trade_date
where u.is_in_universe and (p.is_stale is null or p.is_stale)
