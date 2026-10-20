-- One row per (symbol, fiscal_year, fiscal_quarter): the quarterly fundamentals with the first
-- trading session on or after the date the quarter may be used. A feature at session D may read
-- a quarter only when available_session_seq <= D (point in time). A quarter whose date lies past
-- the calendar's last day has no session yet (NULL).
with next_session as (
    select
        calendar_date,
        min(case when is_trading_day then session_seq end) over (
            order by calendar_date rows between current row and unbounded following
        ) as next_session_seq,
        min(case when is_trading_day then calendar_date end) over (
            order by calendar_date rows between current row and unbounded following
        ) as next_session_date
    from {{ ref('dim_trading_calendar') }}
)

select
    q.*,
    n.next_session_seq as available_session_seq,
    n.next_session_date as available_session_date
from {{ ref('int_fundamentals__quarterly') }} as q
left join next_session as n
    on n.calendar_date = q.available_from_date
