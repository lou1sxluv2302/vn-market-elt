-- From 1 December, the holiday seed must already hold next year's dates
-- (docs/knowledge/market-microstructure.md §12): otherwise the calendar would
-- treat every weekday of the coming year as a trading day, as v1 did for 2027.
with today as (
    select cast({{ dbt.current_timestamp() }} as date) as d
),
next_year as (
    select count(*) as n
    from {{ ref('holidays') }}, today
    where extract(year from holiday_date) = extract(year from today.d) + 1
)
select next_year.n
from next_year, today
where extract(month from today.d) = 12 and next_year.n = 0
