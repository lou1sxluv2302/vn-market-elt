-- One row per pull that changed rows of an earlier pull of the same (source, symbol): the
-- vendor rewrote history (P4, Q1). Staging keeps the newest pull, so prices are right
-- either way; this table makes the rewrites visible. Classes, checked in this order
-- (thresholds and their measurements: dbt_project.yml vars):
--   same_close  no close changed (volume, high or low of a recent session restated);
--   rescale     every close up to the last changed date, changed or not, lies within
--               rounding of one ratio, and the changed rows are (almost) the whole history
--               up to that date (a corporate action re-adjusted);
--   noise       every changed close moved by at most `revision_noise_max_move`;
--   other       anything else: several ratios at once, a window rewritten, a close from
--               or to 0 or null.
with compared as (
    select
        *,
        close_vnd / nullif(old_close_vnd, 0) as close_ratio
    from {{ ref('int_prices__revisions') }}
),

events as (
    select
        _source_id,
        symbol,
        _ingested_at,
        _source_file,
        min(_ingest_partition) as ingest_partition,
        min(trade_date) as first_changed_date,
        max(trade_date) as last_changed_date,
        count(*) as rows_changed,
        sum(case when is_close_changed then 1 else 0 end) as closes_changed,
        sum(case when is_close_changed and close_ratio is null then 1 else 0 end)
            as closes_without_ratio,
        max(case when is_close_changed then abs(close_ratio - 1) end) as max_close_move,
        min(case when is_close_changed then close_ratio end) as min_close_ratio,
        max(case when is_close_changed then close_ratio end) as max_close_ratio,
        max(case when is_close_changed then old_close_vnd end) as largest_old_close_vnd
    from compared
    where is_changed
    group by _source_id, symbol, _ingested_at, _source_file
),

-- The ratio is read where rounding matters least: at the largest old close.
reference as (
    select
        e._source_id, e.symbol, e._ingested_at, e._source_file,
        max(c.close_ratio) as reference_ratio
    from events as e
    join compared as c
        on c._source_id = e._source_id
        and c.symbol = e.symbol
        and c._ingested_at = e._ingested_at
        and c._source_file = e._source_file
        and c.is_close_changed
        and c.old_close_vnd = e.largest_old_close_vnd
    group by e._source_id, e.symbol, e._ingested_at, e._source_file
),

fit as (
    select
        e._source_id, e.symbol, e._ingested_at, e._source_file,
        count(*) as rows_compared_to_last_change,
        -- every row up to the last change, changed or not: a row the vendor left out of a
        -- rescale lies far from the ratio, one that rounding left equal does not
        max(abs(c.close_vnd - r.reference_ratio * c.old_close_vnd)) as max_deviation_vnd
    from events as e
    join compared as c
        on c._source_id = e._source_id
        and c.symbol = e.symbol
        and c._ingested_at = e._ingested_at
        and c._source_file = e._source_file
        and c.trade_date <= e.last_changed_date
    left join reference as r
        on r._source_id = e._source_id
        and r.symbol = e.symbol
        and r._ingested_at = e._ingested_at
        and r._source_file = e._source_file
    group by e._source_id, e.symbol, e._ingested_at, e._source_file
)

select
    e._source_id,
    e.symbol,
    e._ingested_at,
    e._source_file,
    e.ingest_partition,
    e.first_changed_date,
    e.last_changed_date,
    e.rows_changed,
    e.closes_changed,
    f.rows_compared_to_last_change,
    r.reference_ratio,
    e.min_close_ratio,
    e.max_close_ratio,
    e.max_close_move,
    f.max_deviation_vnd,
    case
        when e.closes_changed = 0 then 'same_close'
        when e.closes_without_ratio = 0
            and e.rows_changed >= {{ var('revision_rescale_min_coverage') }}
                * f.rows_compared_to_last_change
            and f.max_deviation_vnd <= {{ var('revision_rescale_max_deviation_vnd') }}
            then 'rescale'
        when e.closes_without_ratio = 0
            and e.max_close_move <= {{ var('revision_noise_max_move') }}
            then 'noise'
        else 'other'
    end as revision_class
from events as e
join fit as f
    on f._source_id = e._source_id
    and f.symbol = e.symbol
    and f._ingested_at = e._ingested_at
    and f._source_file = e._source_file
left join reference as r
    on r._source_id = e._source_id
    and r.symbol = e.symbol
    and r._ingested_at = e._ingested_at
    and r._source_file = e._source_file
