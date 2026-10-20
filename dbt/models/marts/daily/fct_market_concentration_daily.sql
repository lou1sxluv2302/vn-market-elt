-- BI v3 (P5): how concentrated trading is, per session, over in-scope non-stale rows of
-- both exchanges: the fewest symbols whose turnover reaches half / 80 % of the session's
-- total (largest first). Not additive across sessions; the report shows it per session.
with ranked as (
    select
        trade_date,
        turnover_vnd,
        sum(turnover_vnd) over (
            partition by trade_date order by turnover_vnd desc, symbol
            rows between unbounded preceding and current row
        ) as running_vnd,
        sum(turnover_vnd) over (partition by trade_date) as total_vnd
    from {{ ref('fct_price_daily') }}
    where is_in_scope and not is_stale and turnover_vnd > 0
)

select
    trade_date,
    count(*) as traded_symbol_count,
    max(total_vnd) as turnover_vnd,
    -- the first symbol whose running total reaches the share, counted from the top
    sum(case when running_vnd - turnover_vnd < 0.5 * total_vnd then 1 else 0 end)
        as symbols_for_half_turnover,
    sum(case when running_vnd - turnover_vnd < 0.8 * total_vnd then 1 else 0 end)
        as symbols_for_80pct_turnover
from ranked
group by trade_date
