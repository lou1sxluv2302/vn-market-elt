-- One row per calendar day. Inside the observed range a day is a session when at least
-- `min_traded_symbols_per_session` symbols traded (all exchanges, as v1); outside it,
-- weekdays minus the holiday seed. That second rule is what puts 2026-11-24 and the 2027
-- holidays right where v1 had every weekday trading.
with spine as (
    {{ date_spine_days(var('calendar_first_date'), var('calendar_last_date')) }}
),

traded as (
    select trade_date, count(distinct symbol) as traded_symbols
    from {{ ref('int_prices__flagged') }}
    where match_qty > 0
    group by trade_date
),

observed as (
    select trade_date
    from traded
    where traded_symbols >= {{ var('min_traded_symbols_per_session') }}
),

bounds as (
    select min(trade_date) as first_observed, max(trade_date) as last_observed
    from observed
),

days as (
    select
        s.calendar_date,
        {{ is_weekday('s.calendar_date') }} as is_weekday,
        h.status as holiday_status,
        h.occasion as holiday_occasion,
        case
            when s.calendar_date between b.first_observed and b.last_observed then 'observed'
            else 'rule'
        end as calendar_source,
        case
            when s.calendar_date between b.first_observed and b.last_observed
                then o.trade_date is not null
            else {{ is_weekday('s.calendar_date') }} and h.holiday_date is null
        end as is_trading_day
    from spine as s
    cross join bounds as b
    left join observed as o on o.trade_date = s.calendar_date
    left join {{ ref('holidays') }} as h on h.holiday_date = s.calendar_date
),

sequenced as (
    select
        *,
        sum(case when is_trading_day then 1 else 0 end)
            over (order by calendar_date rows between unbounded preceding and current row)
            as trading_days_so_far,
        lead(calendar_date) over (partition by is_trading_day order by calendar_date)
            as next_same_kind_date
    from days
)

select
    calendar_date,
    is_trading_day,
    is_weekday,
    holiday_status,
    holiday_occasion,
    calendar_source,
    case when is_trading_day then trading_days_so_far end as session_seq,
    {{ iso_week_id('calendar_date') }} as trading_week_id,
    extract(year from calendar_date) * 100 + extract(month from calendar_date) as trading_month_id,
    extract(year from calendar_date) as trading_year_id,
    coalesce(
        is_trading_day
        and (next_same_kind_date is null
             or extract(month from next_same_kind_date) <> extract(month from calendar_date)),
        false
    ) as is_month_end_session,
    coalesce(
        is_trading_day
        and (next_same_kind_date is null
             or floor((extract(month from next_same_kind_date) - 1) / 3)
                <> floor((extract(month from calendar_date) - 1) / 3)
             or extract(year from next_same_kind_date) <> extract(year from calendar_date)),
        false
    ) as is_quarter_end_session
from sequenced
