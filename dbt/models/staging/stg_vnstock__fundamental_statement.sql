-- Newest snapshot of v1's financial statements (VCI): one row per symbol, statement, item and
-- fiscal period, long form. Meta rows (report labels, ids) are dropped. Values stay as the
-- source gives them - VND for statement items, the source's own unit for ratios; the zero
-- trap (0 written for an item that does not apply) is handled in the intermediate model.
-- The source has no publication date: v1's `available_from_date` (deadline + 5 days) is kept
-- as `v1_available_from_date` so the intermediate model's own date can be reconciled with it.
with newest as (
    select *
    from {{ source('vnstock', 'fundamental_statement') }}
    where _loaded_at = (select max(_loaded_at) from {{ source('vnstock', 'fundamental_statement') }})
)

select
    symbol,
    statement,
    item_key,
    period_type,
    cast(year as {{ dbt.type_bigint() }}) as fiscal_year,
    cast(quarter as {{ dbt.type_bigint() }}) as fiscal_quarter,
    period_end_date,
    available_from_date as v1_available_from_date,
    value,
    item_all_zero as is_item_all_zero,
    _source_sha256,
    _loaded_at
from newest
where not is_meta
