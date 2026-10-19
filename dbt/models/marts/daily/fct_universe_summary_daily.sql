-- The point-in-time universe per (exchange, trade_date): size, tiers, and the symbols that
-- entered or left it since the symbol's previous session. Counts the flag each session had
-- then - never "ever in the universe" (data-quality-lessons: survivorship).
with flagged as (
    select
        exchange,
        trade_date,
        session_seq,
        symbol,
        liquidity_tier,
        is_in_universe,
        lag(is_in_universe) over (partition by symbol order by session_seq) as was_in_universe
    from {{ ref('fct_universe_daily') }}
)

select
    exchange,
    trade_date,
    max(session_seq) as session_seq,
    sum(case when is_in_universe then 1 else 0 end) as universe_count,
    sum(case when is_in_universe and liquidity_tier = 'HIGH' then 1 else 0 end) as tier_high_count,
    sum(case when is_in_universe and liquidity_tier = 'MEDIUM' then 1 else 0 end)
        as tier_medium_count,
    sum(case when is_in_universe and liquidity_tier = 'LOW' then 1 else 0 end) as tier_low_count,
    sum(case when is_in_universe and not coalesce(was_in_universe, false) then 1 else 0 end)
        as entered_count,
    sum(case when not is_in_universe and was_in_universe then 1 else 0 end) as exited_count
from flagged
group by exchange, trade_date
