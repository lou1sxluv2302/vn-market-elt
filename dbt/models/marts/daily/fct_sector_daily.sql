-- One row per (supersector, trade_date) for the BI sector page: ICB level 2 from dim_symbol,
-- over in-scope, non-stale rows as in fct_market_breadth_daily (both exchanges together).
-- Counts and sums only, so the report builds ratios; median_return_1d_ratio is the one
-- non-additive column. equal_weight_index chains the mean 1D return from the first
-- session, so an N-session sector return is index(t) / index(t - N) - 1.
-- The classification is today's, not point in time: a symbol that changed sector shows
-- in its current one for all history. A symbol without one is in 'none' / "Chưa phân ngành".
with active as (
    select
        s.trade_date,
        s.session_seq,
        coalesce(d.supersector_code, 'none') as supersector_code,
        coalesce(d.supersector_vi, 'Chưa phân ngành') as supersector_vi,
        coalesce(d.supersector_en, 'Unclassified') as supersector_en,
        s.return_1d_ratio,
        s.close_vnd,
        s.ma50_vnd,
        s.ma200_vnd,
        s.is_new_high_52w,
        s.is_new_low_52w,
        s.turnover_vnd,
        s.foreign_net_total_value_vnd,
        {{ median_over('s.return_1d_ratio', "coalesce(d.supersector_code, 'none'), s.trade_date") }}
            as median_return_1d_ratio
    from {{ ref('fct_symbol_session_daily') }} as s
    left join {{ ref('dim_symbol') }} as d
        on d.symbol = s.symbol
    where s.is_in_scope and not s.is_stale
),

counts as (
    select
        supersector_code,
        max(supersector_vi) as supersector_vi,
        max(supersector_en) as supersector_en,
        trade_date,
        max(session_seq) as session_seq,
        count(*) as active_symbol_count,
        sum(case when return_1d_ratio > 0 then 1 else 0 end) as advancing_count,
        sum(case when return_1d_ratio < 0 then 1 else 0 end) as declining_count,
        avg(return_1d_ratio) as mean_return_1d_ratio,
        max(median_return_1d_ratio) as median_return_1d_ratio,
        sum(turnover_vnd) as turnover_vnd,
        sum(turnover_vnd * return_1d_ratio) as turnover_x_return_vnd,
        sum(case when return_1d_ratio is not null then turnover_vnd else 0 end)
            as turnover_with_return_vnd,
        sum(case when ma50_vnd is not null then 1 else 0 end) as ma50_eligible_count,
        sum(case when close_vnd > ma50_vnd then 1 else 0 end) as above_ma50_count,
        sum(case when ma200_vnd is not null then 1 else 0 end) as ma200_eligible_count,
        sum(case when close_vnd > ma200_vnd then 1 else 0 end) as above_ma200_count,
        sum(case when is_new_high_52w then 1 else 0 end) as new_high_52w_count,
        sum(case when is_new_low_52w then 1 else 0 end) as new_low_52w_count,
        sum(foreign_net_total_value_vnd) as foreign_net_value_vnd
    from active
    group by supersector_code, trade_date
)

select
    *,
    exp(
        sum(ln(1 + coalesce(mean_return_1d_ratio, 0))) over (
            partition by supersector_code
            order by trade_date
            rows between unbounded preceding and current row
        )
    ) as equal_weight_index
from counts
