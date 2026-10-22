-- The newest version of each corporate action across every run, full or incremental: one row
-- per event. `exercise_ratio` is the source's ratio (0.10 = 10 % of par for a cash dividend,
-- 10 new shares per 100 for a share issue); `value_per_share_vnd` is the cash amount per share.
-- An event absent from later runs is kept: history does not shrink, and the loader refuses a
-- full run with fewer events per symbol than the previous full run.
with ranked as (
    select
        *,
        row_number() over (partition by event_id order by _loaded_at desc) as version_rank
    from {{ source('vci', 'corporate_actions') }}
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
    _mode,
    _run_id,
    _loaded_at
from ranked
where version_rank = 1
