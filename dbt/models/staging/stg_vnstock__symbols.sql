-- Newest snapshot of the symbol list. Exchange spellings go through the exchange_alias
-- seed; DELISTED maps to no exchange (the source drops it on delisting).
with newest as (
    select *
    from {{ source('vnstock', 'ref_symbols_by_exchange') }}
    where _loaded_at = (select max(_loaded_at) from {{ source('vnstock', 'ref_symbols_by_exchange') }})
)

select
    n.symbol,
    upper(n.type) as instrument_type,
    n.exchange as source_exchange,
    a.exchange,
    coalesce(a.is_in_scope, false) as is_in_scope,
    n.exchange = 'DELISTED' as is_delisted,
    n.organ_name,
    n._loaded_at
from newest as n
left join {{ ref('exchange_alias') }} as a
    on a.source_value = n.exchange
