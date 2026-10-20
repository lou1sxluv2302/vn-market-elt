-- Newest snapshot of the symbol -> ICB classification, one row per symbol and level. The
-- source repeats a few (symbol, level) pairs (3 of 2,046 at level 1, 2026-10-20): the lowest
-- code wins, so the choice never depends on row order. Current classification, not point
-- in time: the vendor gives today's, so history is drawn with today's industries.
with newest as (
    select *
    from {{ source('vnstock', 'ref_symbols_by_industries') }}
    where _loaded_at = (select max(_loaded_at) from {{ source('vnstock', 'ref_symbols_by_industries') }})
),

ranked as (
    select
        symbol,
        cast(icb_level as int) as icb_level,
        icb_code,
        row_number() over (partition by symbol, icb_level order by icb_code) as code_rank
    from newest
)

select symbol, icb_level, icb_code
from ranked
where code_rank = 1
