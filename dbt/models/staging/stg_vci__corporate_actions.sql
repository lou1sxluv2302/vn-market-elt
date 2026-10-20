-- Newest snapshot of the corporate-action pull: one row per event. `exercise_ratio` is the
-- source's ratio (0.10 = 10 % of par for a cash dividend, 10 new shares per 100 for a share
-- issue); `value_per_share_vnd` is the cash amount per share. Dates are the source's.
with newest as (
    select *
    from {{ source('vci', 'corporate_actions') }}
    where _run_id = (
        select _run_id
        from {{ source('vci', 'corporate_actions') }}
        order by _loaded_at desc
        limit 1
    )
)

select
    event_id,
    symbol,
    event_code,
    category,
    event_name_en,
    event_title_en,
    public_date,
    record_date,
    exright_date as ex_rights_date,
    issue_date,
    payout_date,
    exercise_ratio,
    value_per_share as value_per_share_vnd,
    _run_id,
    _loaded_at
from newest
