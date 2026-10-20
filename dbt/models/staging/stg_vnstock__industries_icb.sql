-- Newest snapshot of the ICB tree: one row per code, with the Vietnamese and English names.
select
    icb_code,
    cast(level as int) as icb_level,
    icb_name as icb_name_vi,
    en_icb_name as icb_name_en
from {{ source('vnstock', 'ref_industries_icb') }}
where _loaded_at = (select max(_loaded_at) from {{ source('vnstock', 'ref_industries_icb') }})
