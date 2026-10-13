-- v1 dq 21c. For a symbol the list names with an exchange, dim_security's first period has
-- that exchange; inference from ticks is only for symbols the list lost (it is unreliable on
-- adjusted prices). Fails on: inference preferred over the list.
select s.symbol, s.exchange, l.exchange as list_exchange
from {{ ref('dim_security') }} as s
join {{ ref('stg_vnstock__symbols') }} as l on l.symbol = s.symbol
where l.exchange is not null
    and s.effective_from is null
    and s.exchange is distinct from l.exchange
