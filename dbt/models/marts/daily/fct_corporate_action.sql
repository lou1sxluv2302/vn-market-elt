-- One row per corporate action (event_id) with a type read from the event code and title:
-- cash_dividend (DIV); for share issues (ISS) bonus_issue, stock_dividend, rights_issue,
-- private_placement, else other_issue. The title is the only place the source names the kind
-- of issue; a title it has never used falls to other_issue, never to a guess.
select
    event_id,
    symbol,
    event_code,
    case
        when event_code = 'DIV' then 'cash_dividend'
        when lower(event_title_en) like '%bonus%' then 'bonus_issue'
        when lower(event_title_en) like '%stock dividend%' then 'stock_dividend'
        when lower(event_title_en) like '%right%' then 'rights_issue'
        when lower(event_title_en) like '%private%' then 'private_placement'
        else 'other_issue'
    end as action_type,
    event_title_en,
    public_date,
    record_date,
    ex_rights_date,
    issue_date,
    payout_date,
    exercise_ratio,
    value_per_share_vnd
from {{ ref('stg_vci__corporate_actions') }}
