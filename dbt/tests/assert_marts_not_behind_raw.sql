-- v1 dq 19 + 20 (incident 2026-08-03: silver stood still while bronze advanced, and every
-- other check passed). A date on which the primary source has at least
-- `min_traded_symbols_per_session` traded symbols is in fct_price_daily, unless it is a
-- known bad date. Staging is a view, so it sees raw rows the marts were not rebuilt for.
-- Fails on: raw loaded after the last dbt build.
-- Narrower than v1 dq 19, which counted bronze dates over every source: here the primary
-- source alone, inside the calendar's range, so a fallback-only date or a date the calendar
-- does not span is not checked.
with traded as (
    select trade_date, count(distinct symbol) as traded_symbols
    from {{ ref('stg_vnstock__ohlcv_daily') }}
    where _source_id = '{{ var("primary_price_source") }}'
        and match_qty > 0
        and trade_date between cast('{{ var("calendar_first_date") }}' as date)
                           and cast('{{ var("calendar_last_date") }}' as date)
    group by trade_date
)

select t.trade_date, t.traded_symbols
from traded as t
left join {{ ref('known_bad_dates') }} as b on b.bad_date = t.trade_date
where t.traded_symbols >= {{ var('min_traded_symbols_per_session') }}
    and b.bad_date is null
    and not exists (
        select 1 from {{ ref('fct_price_daily') }} as p where p.trade_date = t.trade_date
    )
