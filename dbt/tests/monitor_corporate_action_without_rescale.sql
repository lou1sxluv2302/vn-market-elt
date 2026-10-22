-- A cash dividend, stock dividend or bonus issue of a HOSE / HNX symbol whose ex-rights date
-- lies inside the raw pull log, with no vendor rewrite (rescale or other) of that symbol's
-- history around it: the vendor did not adjust (or adjusted late). A warning to read, not a
-- fault: the adjusted prices are the vendor's. Any window counts - an illiquid symbol's last
-- session before the ex-date can be weeks earlier. Measured 2026-10-22: 0 such events of 175.
{{ config(severity='warn') }}
with log_window as (  -- from the first pull in the raw log: a rewrite shows from the next one
    select min(_ingest_partition) as first_pull, max(_ingest_partition) as last_pull
    from {{ source('vnstock', 'ohlcv_daily') }}
),

covered as (
    select distinct a.event_id
    from {{ ref('fct_corporate_action') }} as a
    inner join {{ ref('fct_price_revision') }} as r
        on r.symbol = a.symbol
        and r.revision_class in ('rescale', 'other')
        and a.ex_rights_date > r.last_changed_date
        and a.ex_rights_date <= r.ingest_partition
)

select a.event_id, a.symbol, a.action_type, a.ex_rights_date
from {{ ref('fct_corporate_action') }} as a
cross join log_window as w
inner join {{ ref('fct_price_daily') }} as p
    on p.symbol = a.symbol
    and p.trade_date = a.ex_rights_date
    and p.exchange in ('HOSE', 'HNX')
left join covered as c
    on c.event_id = a.event_id
where a.action_type in ('cash_dividend', 'stock_dividend', 'bonus_issue')
    and a.ex_rights_date > w.first_pull
    and a.ex_rights_date <= w.last_pull
    and c.event_id is null
