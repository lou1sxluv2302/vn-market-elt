-- Newest snapshot of v1's foreign flow file: one row per (symbol, trade_date), as v1
-- delivered it - values in VND and quantities in shares, stored as doubles and cast to
-- integers here. Named by trade type (match / put_through / total, flows.md §2.3); whether
-- match + put-through = total is judged in the mart, not here. Room columns stay in raw
-- until a model needs them (their meaning shifted with KRX, flows.md §2.2).
with newest as (
    select *
    from {{ source('vnstock', 'foreign_trade_daily') }}
    where _loaded_at = (select max(_loaded_at) from {{ source('vnstock', 'foreign_trade_daily') }})
)

select
    symbol,
    session_date as trade_date,
    {%- for side in ['buy', 'sell', 'net'] %}
    {%- for kind, src in [('match', 'matched'), ('put_through', 'deal'), ('total', 'total')] %}
    cast(round(fr_{{ side }}_vol_{{ src }}) as {{ dbt.type_bigint() }}) as foreign_{{ side }}_{{ kind }}_qty,
    cast(round(fr_{{ side }}_val_{{ src }}) as {{ dbt.type_bigint() }}) as foreign_{{ side }}_{{ kind }}_value_vnd,
    {%- endfor %}
    {%- endfor %}
    breakdown_valid as is_source_breakdown_valid,
    _source_sha256,
    _loaded_at
from newest
