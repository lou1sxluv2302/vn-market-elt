-- One row per vendor rescale (the whole history rewritten by one ratio) of a HOSE / HNX symbol,
-- checked against the corporate actions (fct_corporate_action) whose ex-rights date falls after
-- its last changed session and on or before the pull. `is_ex_date_shape`: pulled at most
-- `rescale_event_window_days` after that session - the shape of one ex-date adjustment. A longer
-- window holds several events or a rewrite of old history (measured: illiquid symbols whose last
-- session was weeks earlier, and rewrites ending in 2009), so only ex-date shapes are judged.
-- Expected new / old close, P = the old close at the last changed session:
--   cash dividend           (P - D) / P, D = cash per share (else ratio x par);
--   stock dividend / bonus  1 / (1 + r);
--   several events multiply; a rights issue has no expected ratio (its price is not in the
--   data), so a window that holds one is `rights_involved`, not judged.
-- Status: matched (gap <= `rescale_ratio_tolerance`), ratio_differs, rights_involved, no_event.
-- Measured 2026-10-22 on 2.5 months of pulls: 155 of 170 short-window rescales matched within
-- 0.003, median gap 0.0001, p99 0.0081; the unexplained ones were UPCoM symbols, which the
-- corporate-action pull does not cover (hence the exchange filter).
with rescales as (
    select
        r._source_id,
        r.symbol,
        r._ingested_at,
        r._source_file,
        r.ingest_partition,
        r.last_changed_date,
        r.reference_ratio
    from {{ ref('fct_price_revision') }} as r
    inner join {{ ref('fct_price_daily') }} as p
        on p.symbol = r.symbol
        and p.trade_date = r.last_changed_date
        and p.exchange in ('HOSE', 'HNX')
    where r.revision_class = 'rescale'
),

reference_close as (
    select
        r._source_id,
        r.symbol,
        r._ingested_at,
        r._source_file,
        max(v.old_close_vnd) as old_close_vnd
    from rescales as r
    inner join {{ ref('int_prices__revisions') }} as v
        on v._source_id = r._source_id
        and v.symbol = r.symbol
        and v._ingested_at = r._ingested_at
        and v._source_file = r._source_file
        and v.trade_date = r.last_changed_date
    group by r._source_id, r.symbol, r._ingested_at, r._source_file
),

matched_events as (
    select
        r._source_id,
        r.symbol,
        r._ingested_at,
        r._source_file,
        a.event_id,
        a.action_type,
        case
            when a.action_type = 'cash_dividend'
                then (c.old_close_vnd - coalesce(a.value_per_share_vnd, a.exercise_ratio * {{ var('par_value_vnd') }}))
                    / nullif(c.old_close_vnd, 0)
            when a.action_type in ('stock_dividend', 'bonus_issue')
                then 1 / (1 + a.exercise_ratio)
        end as factor
    from rescales as r
    inner join reference_close as c
        on c._source_id = r._source_id
        and c.symbol = r.symbol
        and c._ingested_at = r._ingested_at
        and c._source_file = r._source_file
    inner join {{ ref('fct_corporate_action') }} as a
        on a.symbol = r.symbol
        and a.ex_rights_date > r.last_changed_date
        and a.ex_rights_date <= r.ingest_partition
        and a.action_type in ('cash_dividend', 'stock_dividend', 'bonus_issue', 'rights_issue')
),

per_rescale as (
    select
        _source_id,
        symbol,
        _ingested_at,
        _source_file,
        sum(case when action_type = 'rights_issue' then 1 else 0 end) as rights_events,
        sum(case when action_type <> 'rights_issue' then 1 else 0 end) as adjusting_events,
        exp(sum(case when action_type <> 'rights_issue' and factor > 0 then ln(factor) end))
            as expected_ratio
    from matched_events
    group by _source_id, symbol, _ingested_at, _source_file
)

select
    r._source_id,
    r.symbol,
    r._ingested_at,
    r._source_file,
    r.ingest_partition,
    r.last_changed_date,
    {{ dbt.datediff('r.last_changed_date', 'r.ingest_partition', 'day') }} as window_days,
    {{ dbt.datediff('r.last_changed_date', 'r.ingest_partition', 'day') }}
        <= {{ var('rescale_event_window_days') }} as is_ex_date_shape,
    r.reference_ratio,
    c.old_close_vnd,
    coalesce(e.adjusting_events, 0) as adjusting_events,
    coalesce(e.rights_events, 0) as rights_events,
    e.expected_ratio,
    r.reference_ratio - e.expected_ratio as ratio_gap,
    case
        when coalesce(e.rights_events, 0) > 0 then 'rights_involved'
        when coalesce(e.adjusting_events, 0) = 0 then 'no_event'
        when abs(r.reference_ratio - e.expected_ratio) <= {{ var('rescale_ratio_tolerance') }}
            then 'matched'
        else 'ratio_differs'
    end as status
from rescales as r
left join reference_close as c
    on c._source_id = r._source_id
    and c.symbol = r.symbol
    and c._ingested_at = r._ingested_at
    and c._source_file = r._source_file
left join per_rescale as e
    on e._source_id = r._source_id
    and e.symbol = r.symbol
    and e._ingested_at = r._ingested_at
    and e._source_file = r._source_file
