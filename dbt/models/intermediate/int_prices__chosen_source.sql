-- One row per (symbol, trade_date). Preference: the primary source's clean row, then the
-- fallback's clean row, then the primary's broken row, then the fallback's (a broken row is
-- one v1's structural checks reject; it is dropped in the marts). v1 instead kept whichever
-- source it fetched that day; tools/reconcile_v1_marts.py explains the difference.
with ranked as (
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
        _source_file,
        row_number() over (
            partition by symbol, trade_date
            order by
                case when {{ is_broken_row() }} then 1 else 0 end,
                case when _source_id = '{{ var("primary_price_source") }}' then 0 else 1 end
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
