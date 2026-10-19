-- BI plan B1. Breadth counts only non-stale, in-scope rows (flows.md §4), recounted here
-- from fct_price_daily independently of the model. Fails on: stale rows (volume 0, price
-- copied) or out-of-scope symbols counted as active.
with recount as (
    select exchange, trade_date, count(*) as active_symbol_count
    from {{ ref('fct_price_daily') }}
    where is_in_scope and not is_stale
    group by exchange, trade_date
)

select b.exchange, b.trade_date, b.active_symbol_count, r.active_symbol_count as recounted
from {{ ref('fct_market_breadth_daily') }} as b
left join recount as r
    on r.exchange = b.exchange and r.trade_date = b.trade_date
where r.active_symbol_count is null or r.active_symbol_count != b.active_symbol_count
