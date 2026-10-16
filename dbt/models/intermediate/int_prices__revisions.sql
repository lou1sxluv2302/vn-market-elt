-- Every raw OHLCV row that also exists in an earlier pull, next to the version it replaced
-- (P4, Q1). A pull is one (source, symbol, _ingested_at, file): v1 pulls each symbol on
-- its own. Unchanged rows stay: fct_price_revision needs them to tell a rescale of the
-- whole history from a rewrite of a window. A view: only the mart reads it.
{{ config(materialized='view') }}
with versions as (
    select
        _source_id,
        symbol,
        session_date as trade_date,
        _ingested_at,
        _ingest_partition,
        _source_file,
        open_vnd,
        high_vnd,
        low_vnd,
        close_vnd,
        volume as match_qty,
        lag(open_vnd) over (
            partition by _source_id, symbol, session_date
            order by _ingested_at, _ingest_partition, _source_file
        ) as old_open_vnd,
        lag(high_vnd) over (
            partition by _source_id, symbol, session_date
            order by _ingested_at, _ingest_partition, _source_file
        ) as old_high_vnd,
        lag(low_vnd) over (
            partition by _source_id, symbol, session_date
            order by _ingested_at, _ingest_partition, _source_file
        ) as old_low_vnd,
        lag(close_vnd) over (
            partition by _source_id, symbol, session_date
            order by _ingested_at, _ingest_partition, _source_file
        ) as old_close_vnd,
        lag(volume) over (
            partition by _source_id, symbol, session_date
            order by _ingested_at, _ingest_partition, _source_file
        ) as old_match_qty,
        lag(_ingested_at) over (
            partition by _source_id, symbol, session_date
            order by _ingested_at, _ingest_partition, _source_file
        ) as old_ingested_at
    from {{ source('vnstock', 'ohlcv_daily') }}
)

select
    _source_id,
    symbol,
    trade_date,
    _ingested_at,
    _ingest_partition,
    _source_file,
    close_vnd,
    old_close_vnd,
    close_vnd is distinct from old_close_vnd as is_close_changed,
    (
        open_vnd is distinct from old_open_vnd
        or high_vnd is distinct from old_high_vnd
        or low_vnd is distinct from old_low_vnd
        or close_vnd is distinct from old_close_vnd
        or match_qty is distinct from old_match_qty
    ) as is_changed
from versions
where old_ingested_at is not null
