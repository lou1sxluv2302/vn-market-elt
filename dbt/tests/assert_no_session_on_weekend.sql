-- v1 validate_all B (the make-up Saturday 2026-08-22 is not a session). No Saturday or
-- Sunday is a trading day; the weekday rule cannot make one, only observed data can.
-- Fails on: a source dating a full session on a weekend, which the >= 30 rule accepts.
select calendar_date
from {{ ref('dim_trading_calendar') }}
where is_trading_day and not is_weekday
