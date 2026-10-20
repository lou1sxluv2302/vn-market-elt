-- Foreign and proprietary flow per (exchange, trade_date), summed over in-scope symbols.
-- Totals always; the matched / put-through split is summed only over rows where it is
-- valid, with the count of rows where it is not (flows.md §2.3), so the report can say
-- "split not valid on N symbols" instead of showing a wrong split. `foreign_net_cum_value_vnd`
-- is the running total per exchange.
with priced as (
    select symbol, trade_date, exchange
    from {{ ref('fct_price_daily') }}
    where is_in_scope
),

foreign_flow as (
    select
        p.exchange,
        f.trade_date,
        sum(f.foreign_buy_total_value_vnd) as foreign_buy_value_vnd,
        sum(f.foreign_sell_total_value_vnd) as foreign_sell_value_vnd,
        sum(f.foreign_net_total_value_vnd) as foreign_net_value_vnd,
        sum(case when f.is_breakdown_valid then f.foreign_net_match_value_vnd end)
            as foreign_net_match_value_vnd,
        sum(case when f.is_breakdown_valid then f.foreign_net_put_through_value_vnd end)
            as foreign_net_put_through_value_vnd,
        sum(case when f.is_breakdown_valid then 0 else 1 end) as foreign_split_invalid_count,
        count(*) as foreign_symbol_count
    from {{ ref('fct_foreign_flow_daily') }} as f
    join priced as p
        on p.symbol = f.symbol and p.trade_date = f.trade_date
    group by p.exchange, f.trade_date
),

prop_flow as (
    select
        p.exchange,
        r.trade_date,
        sum(r.prop_net_total_value_vnd) as prop_net_value_vnd,
        sum(case when r.prop_data_available then 1 else 0 end) as prop_symbol_count
    from {{ ref('fct_prop_flow_daily') }} as r
    join priced as p
        on p.symbol = r.symbol and p.trade_date = r.trade_date
    group by p.exchange, r.trade_date
)

select
    coalesce(f.exchange, r.exchange) as exchange,
    coalesce(f.trade_date, r.trade_date) as trade_date,
    f.foreign_buy_value_vnd,
    f.foreign_sell_value_vnd,
    f.foreign_net_value_vnd,
    f.foreign_net_match_value_vnd,
    f.foreign_net_put_through_value_vnd,
    f.foreign_split_invalid_count,
    f.foreign_symbol_count,
    r.prop_net_value_vnd,
    r.prop_symbol_count,
    -- running total per exchange since the first session (bi-conventions: cumulative state
    -- lives here, the report takes a window as the difference of two of these)
    sum(coalesce(f.foreign_net_value_vnd, 0)) over (
        partition by coalesce(f.exchange, r.exchange)
        order by coalesce(f.trade_date, r.trade_date)
        rows between unbounded preceding and current row
    ) as foreign_net_cum_value_vnd
from foreign_flow as f
full outer join prop_flow as r
    on r.exchange = f.exchange and r.trade_date = f.trade_date
