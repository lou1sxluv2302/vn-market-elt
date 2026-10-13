-- One row per symbol and effective period (SCD2 on exchange). Exchange comes from the
-- newest symbol list; for a symbol the list marks DELISTED or no longer lists, it is
-- inferred from price ticks as v1 did and flagged. An announced market-wide move
-- (exchange_changes, applies_to every listed stock) splits a listed symbol's row at its
-- effective date: before it the old exchange, from it the new one.
-- Known gap (ADR-0028): no listing or delisting dates; the vendor has them for under
-- half the symbols, so the universe uses "has traded" instead.
with priced_symbols as (
    select
        symbol,
        count(case when close_vnd < {{ var('inference_low_price_below_vnd') }} then 1 end) as n_low,
        count(case when close_vnd < {{ var('inference_low_price_below_vnd') }}
                   and mod(close_vnd, {{ var('inference_hnx_tick_vnd') }}) = 0 then 1 end)
            as n_low_on_hnx_tick,
        count(case when close_vnd between {{ var('inference_low_price_below_vnd') }}
                                      and {{ var('inference_mid_price_max_vnd') }} then 1 end)
            as n_mid,
        count(case when close_vnd between {{ var('inference_low_price_below_vnd') }}
                                      and {{ var('inference_mid_price_max_vnd') }}
                   and mod(close_vnd, {{ var('inference_hnx_tick_vnd') }}) = 0 then 1 end)
            as n_mid_on_hnx_tick
    from {{ ref('int_prices__flagged') }}
    group by symbol
),

inferred as (
    select
        symbol,
        case
            when n_low >= {{ var('exchange_inference_min_rows') }}
                then case when n_low_on_hnx_tick > {{ var('exchange_inference_hnx_share') }} * n_low
                          then 'HNX' else 'HOSE' end
            when n_mid >= {{ var('exchange_inference_min_rows') }}
                then case when n_mid_on_hnx_tick > {{ var('exchange_inference_hnx_share') }} * n_mid
                          then 'HNX' else 'HOSE' end
        end as inferred_exchange
    from priced_symbols
),

current_exchange as (
    select
        p.symbol,
        coalesce(l.exchange, i.inferred_exchange) as exchange,
        l.exchange is null and i.inferred_exchange is not null as exchange_is_inferred,
        -- not in the newest list at all: gone, so treated as delisted
        coalesce(l.is_delisted, true) as is_delisted,
        l.symbol is not null as is_in_symbol_list,
        l.instrument_type
    from priced_symbols as p
    left join {{ ref('stg_vnstock__symbols') }} as l on l.symbol = p.symbol
    left join inferred as i on i.symbol = p.symbol
),

moves as (
    select from_exchange, to_exchange, effective_from
    from {{ ref('exchange_changes') }}
    where applies_to = 'every_listed_stock'
),

periods as (
    -- Listed symbols a move applies to: two periods, split at its date.
    select
        c.symbol, c.exchange, c.exchange_is_inferred, c.is_delisted, c.is_in_symbol_list,
        c.instrument_type, cast(null as date) as effective_from, m.effective_from as effective_to
    from current_exchange as c
    join moves as m on m.from_exchange = c.exchange and not c.is_delisted
    union all
    select
        c.symbol, m.to_exchange, c.exchange_is_inferred, c.is_delisted, c.is_in_symbol_list,
        c.instrument_type, m.effective_from, cast(null as date)
    from current_exchange as c
    join moves as m on m.from_exchange = c.exchange and not c.is_delisted
    union all
    -- Everyone else: one open period.
    select
        c.symbol, c.exchange, c.exchange_is_inferred, c.is_delisted, c.is_in_symbol_list,
        c.instrument_type, cast(null as date), cast(null as date)
    from current_exchange as c
    where c.is_delisted
        or not exists (select 1 from moves as m where m.from_exchange = c.exchange)
)

select
    p.symbol,
    p.exchange,
    coalesce(a.is_in_scope, false) as is_in_scope,
    p.exchange_is_inferred,
    p.is_delisted,
    p.is_in_symbol_list,
    p.instrument_type,
    p.effective_from,
    p.effective_to
from periods as p
left join {{ ref('exchange_alias') }} as a on a.source_value = p.exchange
