-- Point-in-time universe, one row per (symbol, trade_date) of fct_price_daily, with the
-- first reason a row is out. In: exchange in scope on that date (HOSE, HNX), traded (not
-- stale; null-stale counts as out, as v1), liquidity tier in `universe_tiers`.
select
    p.symbol,
    p.trade_date,
    p.session_seq,
    p.exchange,
    l.liquidity_tier,
    l.adv_20d_vnd,
    case
        when not p.is_in_scope then 'exchange_out_of_scope'
        when p.is_stale is null or p.is_stale then 'stale'
        when l.liquidity_tier = 'INSUFFICIENT' then 'insufficient_history'
        when l.liquidity_tier not in ('{{ var("universe_tiers") | join("', '") }}')
            then 'below_liquidity_floor'
    end as exclusion_reason,
    p.is_in_scope
    and p.is_stale = false
    and coalesce(l.liquidity_tier in ('{{ var("universe_tiers") | join("', '") }}'), false)
        as is_in_universe
from {{ ref('fct_price_daily') }} as p
left join {{ ref('fct_liquidity_daily') }} as l
    on l.symbol = p.symbol and l.trade_date = p.trade_date
