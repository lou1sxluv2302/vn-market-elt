-- Newest snapshot of v1's index table: one row per (index_code, trade_date), in index
-- points. v1 kept index history only in its database (legacy rows carry no source id;
-- from 2026-03-09 they come from vnstock_quote).
with newest as (
    select *
    from {{ source('vnstock', 'index_daily') }}
    where _loaded_at = (select max(_loaded_at) from {{ source('vnstock', 'index_daily') }})
)

select
    index_code,
    session_date as trade_date,
    open as open_points,
    high as high_points,
    low as low_points,
    close as close_points,
    volume as source_volume_qty,
    _source_id,
    _source_sha256,
    _loaded_at
from newest
