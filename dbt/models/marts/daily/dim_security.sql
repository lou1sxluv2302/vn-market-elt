-- One row per symbol and effective period (SCD2 on exchange). Exchange comes from the
-- newest symbol list; for a delisted symbol the list has lost it, so it is inferred from
-- price ticks as v1 did and flagged. An announced market-wide move (exchange_changes)
-- splits the row at its effective date: before it the old exchange, from it the new one.
with priced_symbols as (
    select
        symbol,
        count(case when close_vnd < 10000 then 1 end) as n_low,
        count(case when close_vnd < 10000 and mod(close_vnd, 100) = 0 then 1 end) as n_low_100,
        count(case when close_vnd between 10000 and 49999 then 1 end) as n_mid,
        count(case when close_vnd between 10000 and 49999 and mod(close_vnd, 100) = 0 then 1 end)
            as n_mid_100
    from {{ ref('int_prices__flagged') }}
    group by symbol
),

inferred as (
    select
        symbol,
        case
            when n_low >= {{ var('exchange_inference_min_rows') }}
                then case when n_low_100 > {{ var('exchange_inference_hnx_share') }} * n_low
                          then 'HNX' else 'HOSE' end
            when n_mid >= {{ var('exchange_inference_min_rows') }}
                then case when n_mid_100 > {{ var('exchange_inference_hnx_share') }} * n_mid
                          then 'HNX' else 'HOSE' end
        end as inferred_exchange
    from priced_symbols
),

current_exchange as (
    select
        p.symbol,
        coalesce(l.exchange, i.inferred_exchange) as exchange,
        l.exchange is null and i.inferred_exchange is not null as exchange_is_inferred,
        coalesce(l.is_delisted, false) as is_delisted,
        l.instrument_type
    from priced_symbols as p
    left join {{ ref('stg_vnstock__symbols') }} as l on l.symbol = p.symbol
    left join inferred as i on i.symbol = p.symbol
),

periods as (
    -- Symbols an announced move applies to: two periods, split at its date.
    select c.*, cast(null as date) as effective_from, x.effective_from as effective_to
    from current_exchange as c
    join {{ ref('exchange_changes') }} as x
        on x.from_exchange = c.exchange and not c.is_delisted
    union all
    select
        c.symbol, x.to_exchange as exchange, c.exchange_is_inferred, c.is_delisted,
        c.instrument_type, x.effective_from, x.effective_to
    from current_exchange as c
    join {{ ref('exchange_changes') }} as x
        on x.from_exchange = c.exchange and not c.is_delisted
    union all
    -- Everyone else: one open period.
    select c.*, cast(null as date) as effective_from, cast(null as date) as effective_to
    from current_exchange as c
    where not exists (
        select 1 from {{ ref('exchange_changes') }} as x
        where x.from_exchange = c.exchange and not c.is_delisted
    )
)

select
    p.symbol,
    p.exchange,
    coalesce(a.is_in_scope, false) as is_in_scope,
    p.exchange_is_inferred,
    p.is_delisted,
    p.instrument_type,
    p.effective_from,
    p.effective_to
from periods as p
left join {{ ref('exchange_alias') }} as a on a.source_value = p.exchange
