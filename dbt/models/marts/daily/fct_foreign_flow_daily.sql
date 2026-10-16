-- Foreign flow per (symbol, trade_date): totals always; the match / put-through split only
-- where it is valid (flows.md §2.3, macro null_invalid_flow_split). Use match for every measure.
{{ null_invalid_flow_split(ref('stg_vnstock__foreign_trade'), 'foreign', var('foreign_breakdown_valid_from')) }}
