-- Latest-wins per source: the newest pull of each (source, symbol, trade_date).
-- Order: newest _ingested_at, then newest ingest partition, then the later file.
-- row_number in a subquery rather than QUALIFY, which Athena (phase X2) lacks.
with pulls as (
    select
        _source_id,
        symbol,
        session_date as trade_date,
        open_vnd,
        high_vnd,
        low_vnd,
        close_vnd,
        volume as match_qty,
        _ingested_at,
        _ingest_partition,
        _source_file,
        row_number() over (
            partition by _source_id, symbol, session_date
            order by _ingested_at desc, _ingest_partition desc, _source_file desc
        ) as pull_rank
    from {{ source('vnstock', 'ohlcv_daily') }}
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
from pulls
where pull_rank = 1
