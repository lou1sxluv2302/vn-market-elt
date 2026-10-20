-- One row per symbol for the BI report: its current exchange (dim_security's open period)
-- and its ICB industry (level 1) and supersector (level 2) in Vietnamese and English.
-- The classification is today's, not point in time (stg_vnstock__symbol_industries);
-- a symbol without one reads "Chưa phân ngành" / "Unclassified".
with current_security as (
    select symbol, exchange, is_in_scope, is_delisted
    from {{ ref('dim_security') }}
    where effective_to is null
),

levels as (
    select
        s.symbol,
        s.icb_level,
        i.icb_code,
        i.icb_name_vi,
        i.icb_name_en
    from {{ ref('stg_vnstock__symbol_industries') }} as s
    join {{ ref('stg_vnstock__industries_icb') }} as i
        on i.icb_code = s.icb_code and i.icb_level = s.icb_level
    where s.icb_level in (1, 2)
)

select
    c.symbol,
    c.exchange,
    c.is_in_scope,
    c.is_delisted,
    l1.icb_code as industry_code,
    coalesce(l1.icb_name_vi, 'Chưa phân ngành') as industry_vi,
    coalesce(l1.icb_name_en, 'Unclassified') as industry_en,
    l2.icb_code as supersector_code,
    coalesce(l2.icb_name_vi, 'Chưa phân ngành') as supersector_vi,
    coalesce(l2.icb_name_en, 'Unclassified') as supersector_en
from current_security as c
left join levels as l1
    on l1.symbol = c.symbol and l1.icb_level = 1
left join levels as l2
    on l2.symbol = c.symbol and l2.icb_level = 2
