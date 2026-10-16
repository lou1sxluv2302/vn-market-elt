-- Foreign flow per (symbol, trade_date): totals always; the match / put-through split only
-- where it is valid (flows.md §2.3, macro flow_with_breakdown). Use match for every measure.
{{ flow_with_breakdown(ref('stg_vnstock__foreign_trade'), 'foreign', var('foreign_breakdown_valid_from')) }}
