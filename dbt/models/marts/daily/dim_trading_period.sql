-- Trading periods for the BI report (bi-conventions §1, §6): one row per week, month and
-- year, with the sessions it holds and whether it is complete - its last calendar day is on
-- or before the last observed session. One table, `period_type` tells them apart, so the
-- rule for "complete" lives once.
with calendar as (
    select
        calendar_date, is_trading_day, calendar_source,
        trading_week_id, trading_month_id, trading_year_id
    from {{ ref('dim_trading_calendar') }}
),

as_of as (
    select max(calendar_date) as last_session
    from calendar
    where calendar_source = 'observed' and is_trading_day
),

periods as (
    select 'week' as period_type, trading_week_id as period_id, calendar_date, is_trading_day
    from calendar
    union all
    select 'month', trading_month_id, calendar_date, is_trading_day from calendar
    union all
    select 'year', trading_year_id, calendar_date, is_trading_day from calendar
)

select
    p.period_type,
    p.period_id,
    min(p.calendar_date) as first_calendar_date,
    max(p.calendar_date) as last_calendar_date,
    sum(case when p.is_trading_day then 1 else 0 end) as session_count,
    max(p.calendar_date) <= max(a.last_session) as is_period_complete
from periods as p
cross join as_of as a
group by p.period_type, p.period_id
