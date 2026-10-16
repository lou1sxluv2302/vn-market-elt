-- Proprietary flow per (symbol, trade_date), best-effort (flows.md §3.3): rows exist only
-- where the source had data (history from 2020, a 50-session gap in 2022). Same split rule
-- as foreign flow; the source starts after the foreign cut-off, so no date floor applies.
with flow as (
    {{ flow_with_breakdown(ref('stg_vnstock__prop_trade'), 'prop') }}
)

select
    *,
    prop_net_total_value_vnd is not null as prop_data_available
from flow
