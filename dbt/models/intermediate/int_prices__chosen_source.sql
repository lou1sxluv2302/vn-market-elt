-- One row per (symbol, trade_date): the primary source's latest pull, the fallback's only
-- where the primary has none. (v1 instead kept whichever source it fetched that day; the
-- difference is counted by tools/reconcile_v1_marts.py.)
with ranked as (
    select
        *,
        row_number() over (
            partition by symbol, trade_date
            order by case when _source_id = '{{ var("primary_price_source") }}' then 0 else 1 end
        ) as source_rank
    from {{ ref('stg_vnstock__ohlcv_daily') }}
    where _source_id in ('{{ var("primary_price_source") }}', '{{ var("fallback_price_source") }}')
)

select
    _source_id,
    symbol,
    trade_date,
    open_vnd,
    high_vnd,
    low_vnd,
    close_vnd,
    match_qty,
    _ingested_at,
    _ingest_partition,
    _source_file
from ranked
where source_rank = 1
