-- Index levels per (index_code, trade_date), in index points. One spliced series in v1
-- (data-sources.md §5): legacy rows to 2026-03-06, vnstock_quote from 2026-03-09.
select
    index_code,
    trade_date,
    open_points,
    high_points,
    low_points,
    close_points,
    source_volume_qty,
    _source_id
from {{ ref('stg_vnstock__index_daily') }}
