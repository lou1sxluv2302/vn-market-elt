-- BI plan v2. Every active symbol-session sits in exactly one supersector: the sector
-- counts of a session add up to the breadth counts of both exchanges. Fails on: a symbol
-- dropped by the sector join, counted in two sectors, or a stale row counted.
with sectors as (
    select trade_date, sum(active_symbol_count) as active_symbol_count
    from {{ ref('fct_sector_daily') }}
    group by trade_date
),

breadth as (
    select trade_date, sum(active_symbol_count) as active_symbol_count
    from {{ ref('fct_market_breadth_daily') }}
    group by trade_date
)

select b.trade_date, b.active_symbol_count, s.active_symbol_count as in_sectors
from breadth as b
left join sectors as s
    on s.trade_date = b.trade_date
where s.active_symbol_count is null or s.active_symbol_count != b.active_symbol_count
