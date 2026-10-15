-- v1 dq 21d's monitor (incident 2026-08-06: one series chained from two sources' adjustment
-- bases). Non-stale fallback rows of symbols ever in the universe stay at or below the
-- ceiling measured on prod (`dq_fallback_rows_ceiling`, dbt_project.yml). A warning: the
-- clean-row rule puts some rows there by design; a rise means a source stopped for a
-- symbol that trades. Fails on: fallback rows growing past the measured count.
{{ config(severity='warn') }}
with universe_symbols as (
    select distinct symbol from {{ ref('fct_universe_daily') }} where is_in_universe
),

counted as (
    select count(*) as fallback_rows
    from {{ ref('fct_price_daily') }}
    where _source_id = '{{ var("fallback_price_source") }}'
        and is_stale = false
        and symbol in (select symbol from universe_symbols)
)

select fallback_rows
from counted
where fallback_rows > {{ var('dq_fallback_rows_ceiling') }}
