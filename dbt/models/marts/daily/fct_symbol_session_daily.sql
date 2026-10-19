-- The one symbol-level fact the BI report imports: one row per (symbol, trade_date) of
-- fct_price_daily, with return, moving averages, 52-week flags, liquidity, universe
-- membership and foreign flow of that session. No new rule lives here: every column comes
-- from the model that owns it.
select
    i.symbol,
    i.trade_date,
    i.session_seq,
    i.exchange,
    i.is_in_scope,
    i.is_stale,
    i.close_vnd,
    i.reference_vnd,
    i.return_1d_ratio,
    i.ma20_vnd,
    i.ma50_vnd,
    i.ma200_vnd,
    i.is_new_high_52w,
    i.is_new_low_52w,
    p.match_qty,
    p.turnover_vnd,
    l.adv_20d_vnd,
    l.liquidity_tier,
    coalesce(u.is_in_universe, false) as is_in_universe,
    f.foreign_buy_total_value_vnd,
    f.foreign_sell_total_value_vnd,
    f.foreign_net_total_value_vnd
from {{ ref('int_prices__indicators') }} as i
join {{ ref('fct_price_daily') }} as p
    on p.symbol = i.symbol and p.trade_date = i.trade_date
left join {{ ref('fct_liquidity_daily') }} as l
    on l.symbol = i.symbol and l.trade_date = i.trade_date
left join {{ ref('fct_universe_daily') }} as u
    on u.symbol = i.symbol and u.trade_date = i.trade_date
left join {{ ref('fct_foreign_flow_daily') }} as f
    on f.symbol = i.symbol and f.trade_date = i.trade_date
