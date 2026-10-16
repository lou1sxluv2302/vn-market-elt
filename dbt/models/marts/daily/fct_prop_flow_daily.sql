-- Proprietary flow per (symbol, trade_date), best-effort (flows.md §3.3). The grain is sparse:
-- rows exist only where the source had data (history from 2020, a 50-session gap in 2022),
-- so prop_data_available says only that this row's net total is present; marking missing
-- sessions needs a symbol x session spine (a later model). Same split rule as foreign flow;
-- the source starts after the foreign cut-off, so no date floor applies.
with flow as (
    {{ null_invalid_flow_split(ref('stg_vnstock__prop_trade'), 'prop') }}
)

select
    symbol,
    trade_date,
    {%- for side in ['buy', 'sell', 'net'] %}{% for kind in ['match', 'put_through', 'total'] %}{% for unit in ['qty', 'value_vnd'] %}
    prop_{{ side }}_{{ kind }}_{{ unit }},
    {%- endfor %}{% endfor %}{% endfor %}
    is_breakdown_valid,
    is_source_breakdown_valid,
    prop_net_total_value_vnd is not null as prop_data_available
from flow
