-- v1 dq 18. Each watched symbol misses at most `dq_watched_max_missing_sessions` sessions of
-- the watched window (symbols and window: dbt_project.yml, v1's choices).
-- Fails on: a pull that lost part of a liquid symbol's history (a month cut by the source).
with expected as (
    select count(*) as n
    from {{ ref('dim_trading_calendar') }}
    where is_trading_day
        and calendar_date between cast('{{ var("dq_watched_from") }}' as date)
                              and cast('{{ var("dq_watched_to") }}' as date)
),

watched as (
    {% for s in var('dq_watched_symbols') %}
    select '{{ s }}' as symbol{% if not loop.last %} union all{% endif %}
    {% endfor %}
),

got as (
    select symbol, count(*) as n
    from {{ ref('fct_price_daily') }}
    where trade_date between cast('{{ var("dq_watched_from") }}' as date)
                         and cast('{{ var("dq_watched_to") }}' as date)
    group by symbol
)

select w.symbol, e.n - coalesce(g.n, 0) as missing_sessions
from watched as w
cross join expected as e
left join got as g on g.symbol = w.symbol
where e.n - coalesce(g.n, 0) > {{ var('dq_watched_max_missing_sessions') }}
