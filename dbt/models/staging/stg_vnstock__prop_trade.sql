-- Newest snapshot of v1's proprietary flow file: one row per (symbol, trade_date), VND and
-- shares cast to integers, named by trade type. Best-effort data (flows.md §3.3): history
-- starts in 2020 with a 50-session gap in 2022; nothing downstream may require it.
with newest as (
    select *
    from {{ source('vnstock', 'prop_trade_daily') }}
    where _loaded_at = (select max(_loaded_at) from {{ source('vnstock', 'prop_trade_daily') }})
)

select
    symbol,
    session_date as trade_date,
    {%- for side in ['buy', 'sell', 'net'] %}
    {%- for kind, src in [('match', 'matched'), ('put_through', 'deal'), ('total', 'total')] %}
    cast(round(prop_{{ side }}_vol_{{ src }}) as {{ dbt.type_bigint() }}) as prop_{{ side }}_{{ kind }}_qty,
    cast(round(prop_{{ side }}_val_{{ src }}) as {{ dbt.type_bigint() }}) as prop_{{ side }}_{{ kind }}_value_vnd,
    {%- endfor %}
    {%- endfor %}
    breakdown_valid as is_source_breakdown_valid,
    _source_sha256,
    _loaded_at
from newest
