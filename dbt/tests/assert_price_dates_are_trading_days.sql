-- v1 dq 5. Every price row falls on a trading day of the calendar.
-- Fails on: a row kept on a day the calendar says is not a session (a Saturday pull, a
-- partial day), e.g. when the mart joins the calendar without is_trading_day.
select p.symbol, p.trade_date
from {{ ref('fct_price_daily') }} as p
left join {{ ref('dim_trading_calendar') }} as c
    on c.calendar_date = p.trade_date and c.is_trading_day
where c.calendar_date is null
