-- BI plan B1. The universe size per session equals the number of symbols flagged in the
-- universe on that session (point in time). Fails on: a count of every listed symbol, or of
-- every symbol that was ever in the universe (survivorship, data-quality-lessons).
with recount as (
    select exchange, trade_date, sum(case when is_in_universe then 1 else 0 end) as universe_count
    from {{ ref('fct_universe_daily') }}
    group by exchange, trade_date
)

select s.exchange, s.trade_date, s.universe_count, r.universe_count as recounted
from {{ ref('fct_universe_summary_daily') }} as s
left join recount as r
    on r.exchange = s.exchange and r.trade_date = s.trade_date
where r.universe_count is null or r.universe_count != s.universe_count
