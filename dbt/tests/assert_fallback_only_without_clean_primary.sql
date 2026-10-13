-- v1 dq 21d, rewritten for ADR-0028 decision 7. A price row comes from the fallback source
-- only when the primary has no clean row for that key.
-- Fails on: a source preference that lets the fallback win over a clean primary row.
select p.symbol, p.trade_date
from {{ ref('fct_price_daily') }} as p
join {{ ref('stg_vnstock__ohlcv_daily') }} as o
    on o.symbol = p.symbol
    and o.trade_date = p.trade_date
    and o._source_id = '{{ var("primary_price_source") }}'
where p._source_id = '{{ var("fallback_price_source") }}'
    and not {{ is_broken_row('o.') }}
