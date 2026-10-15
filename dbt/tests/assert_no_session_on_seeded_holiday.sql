-- v1 validate_all B (Tet 2026). No seeded holiday is a trading day.
-- Fails on: the weekday rule ignoring the holiday seed - how v1 got 2026-11-24 and 2027 wrong.
select c.calendar_date, h.occasion
from {{ ref('dim_trading_calendar') }} as c
join {{ ref('holidays') }} as h on h.holiday_date = c.calendar_date
where c.is_trading_day
