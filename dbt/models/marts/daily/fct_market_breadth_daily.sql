-- Market breadth per (exchange, trade_date), docs/knowledge/flows.md §4. Counts only
-- non-stale, in-scope rows; ratios are left to the report (sum of counts over sum of
-- denominators), so any grouping of exchanges stays exact. `pct_advancing` excludes
-- unchanged symbols: its denominator is advancing + declining. No ceiling / floor counts:
-- prices are adjusted, so they would be false (flows.md §4, ADR-0028).
with active as (
    select *
    from {{ ref('int_prices__indicators') }}
    where is_in_scope and not is_stale
),

turnover_ranked as (
    select
        p.exchange,
        p.trade_date,
        p.turnover_vnd,
        row_number() over (
            partition by p.exchange, p.trade_date order by p.turnover_vnd desc, p.symbol
        ) as turnover_rank
    from {{ ref('fct_price_daily') }} as p
    where p.is_in_scope and not p.is_stale
),

turnover as (
    select
        exchange,
        trade_date,
        sum(turnover_vnd) as turnover_vnd,
        sum(
            case when turnover_rank <= {{ var('top_turnover_symbols') }} then turnover_vnd else 0 end
        ) as top10_turnover_vnd
    from turnover_ranked
    group by exchange, trade_date
),

counts as (
    select
        exchange,
        trade_date,
        max(session_seq) as session_seq,
        count(*) as active_symbol_count,
        sum(case when return_1d_ratio > 0 then 1 else 0 end) as advancing_count,
        sum(case when return_1d_ratio < 0 then 1 else 0 end) as declining_count,
        sum(case when return_1d_ratio = 0 then 1 else 0 end) as unchanged_count,
        sum(case when ma50_vnd is not null then 1 else 0 end) as ma50_eligible_count,
        sum(case when close_vnd > ma50_vnd then 1 else 0 end) as above_ma50_count,
        sum(case when ma200_vnd is not null then 1 else 0 end) as ma200_eligible_count,
        sum(case when close_vnd > ma200_vnd then 1 else 0 end) as above_ma200_count,
        sum(case when is_new_high_52w is not null then 1 else 0 end) as high_low_eligible_count,
        sum(case when is_new_high_52w then 1 else 0 end) as new_high_52w_count,
        sum(case when is_new_low_52w then 1 else 0 end) as new_low_52w_count
    from active
    group by exchange, trade_date
)

select
    c.exchange,
    c.trade_date,
    c.session_seq,
    c.active_symbol_count,
    c.advancing_count,
    c.declining_count,
    c.unchanged_count,
    c.ma50_eligible_count,
    c.above_ma50_count,
    c.ma200_eligible_count,
    c.above_ma200_count,
    c.high_low_eligible_count,
    c.new_high_52w_count,
    c.new_low_52w_count,
    sum(c.advancing_count - c.declining_count) over (
        partition by c.exchange
        order by c.trade_date
        rows between unbounded preceding and current row
    ) as ad_line,
    t.turnover_vnd,
    t.top10_turnover_vnd
from counts as c
left join turnover as t
    on t.exchange = c.exchange and t.trade_date = c.trade_date
