-- The VN30 / HNX30 ledger as loaded: one row per (as_of_date, group_code, symbol).
select
    as_of_date,
    group_code,
    symbol,
    _loaded_at
from {{ source('vci', 'index_membership_snapshot') }}
