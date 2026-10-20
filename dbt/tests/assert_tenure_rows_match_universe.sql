-- BI v3. Every universe row has exactly one tenure row: per session, the tenure mart's row
-- count equals the universe flags' count (fct_universe_daily, recounted here). Fails on: a
-- run counted for rows out of the universe, or a row dropped or doubled.
with flags as (
    select trade_date, count(*) as n
    from {{ ref('fct_universe_daily') }}
    where is_in_universe
    group by trade_date
),

tenure as (
    select trade_date, count(*) as n
    from {{ ref('fct_universe_tenure_daily') }}
    group by trade_date
)

select f.trade_date, f.n as in_universe, t.n as tenure_rows
from flags as f
full outer join tenure as t
    on t.trade_date = f.trade_date
where f.n is null or t.n is null or f.n != t.n
