-- BI v3 (P5): for each universe row, how many sessions in a row the symbol has been in the
-- point-in-time universe up to that session (1 = it joined that session). Rows out of the
-- universe are left out. Sessions are the symbol's own price rows (fct_universe_daily),
-- so a session without a price row neither extends nor breaks the run.
with flags as (
    select
        symbol,
        trade_date,
        is_in_universe,
        case
            when is_in_universe = lag(is_in_universe) over (partition by symbol order by trade_date)
                then 0
            else 1
        end as starts_run
    from {{ ref('fct_universe_daily') }}
),

runs as (
    select
        *,
        sum(starts_run) over (
            partition by symbol order by trade_date rows between unbounded preceding and current row
        ) as run_id
    from flags
)

select
    symbol,
    trade_date,
    row_number() over (partition by symbol, run_id order by trade_date) as tenure_sessions
from runs
where is_in_universe
