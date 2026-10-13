-- v1 validate_all D. In each falling-market window the universe holds at least
-- `dq_falling_market_min_symbols` distinct symbols (windows and floor: v1's choices).
-- Fails on: a liquidity threshold in the wrong unit, which empties the universe exactly
-- where survivorship would hide it.
with windows as (
    {% for w in var('dq_falling_market_windows') %}
    select
        cast('{{ w["from"] }}' as date) as window_from,
        cast('{{ w["to"] }}' as date) as window_to{% if not loop.last %} union all{% endif %}
    {% endfor %}
)

select w.window_from, w.window_to, count(distinct u.symbol) as symbols
from windows as w
left join {{ ref('fct_universe_daily') }} as u
    on u.trade_date between w.window_from and w.window_to and u.is_in_universe
group by w.window_from, w.window_to
having count(distinct u.symbol) < {{ var('dq_falling_market_min_symbols') }}
