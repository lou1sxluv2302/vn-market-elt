-- ADV20 point-in-time: mean turnover over the previous `adv_window_rows` non-stale rows of
-- the symbol, never the current one (look-ahead). Fewer than `adv_min_rows` rows in the
-- window: insufficient. Tiers are v1's provisional, unmeasured thresholds (dbt_project.yml).
with tradable as (
    select symbol, trade_date, session_seq, turnover_vnd
    from {{ ref('fct_price_daily') }}
    where is_stale = false
),

windowed as (
    select
        symbol,
        trade_date,
        session_seq,
        turnover_vnd,
        avg(turnover_vnd) over w as adv_20d_vnd,
        count(*) over w as adv_rows
    from tradable
    window w as (
        partition by symbol order by session_seq
        rows between {{ var('adv_window_rows') }} preceding and 1 preceding
    )
)

select
    symbol,
    trade_date,
    session_seq,
    turnover_vnd,
    adv_20d_vnd,
    adv_rows,
    case
        when adv_rows < {{ var('adv_min_rows') }} then 'INSUFFICIENT'
        when adv_20d_vnd >= {{ var('liquidity_tier_high_vnd') }} then 'HIGH'
        when adv_20d_vnd >= {{ var('liquidity_tier_medium_vnd') }} then 'MEDIUM'
        when adv_20d_vnd >= {{ var('liquidity_tier_low_vnd') }} then 'LOW'
        else 'REJECT'
    end as liquidity_tier
from windowed
