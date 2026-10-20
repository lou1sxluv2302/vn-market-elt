-- BI v3 (P3 flows): per (symbol, trade_date) with a foreign net value, the current run of
-- sessions with the same sign of foreign net (total, put-through included) and the run's
-- net sum. A zero net breaks a run and starts its own. Rows without a value are left out,
-- so a session the source misses neither extends nor breaks a run (the run counts sessions
-- with data). A running count is awkward in DAX over millions of rows: it is computed here.
with flows as (
    select
        symbol,
        trade_date,
        foreign_net_total_value_vnd as net_vnd,
        sign(foreign_net_total_value_vnd) as net_sign
    from {{ ref('fct_foreign_flow_daily') }}
    where foreign_net_total_value_vnd is not null
),

marked as (
    select
        *,
        case
            when net_sign = lag(net_sign) over (partition by symbol order by trade_date) then 0
            else 1
        end as starts_run
    from flows
),

runs as (
    select
        *,
        sum(starts_run) over (
            partition by symbol order by trade_date rows between unbounded preceding and current row
        ) as run_id
    from marked
)

select
    symbol,
    trade_date,
    net_sign,
    row_number() over (partition by symbol, run_id order by trade_date) as run_sessions,
    sum(net_vnd) over (
        partition by symbol, run_id order by trade_date
        rows between unbounded preceding and current row
    ) as run_net_vnd
from runs
