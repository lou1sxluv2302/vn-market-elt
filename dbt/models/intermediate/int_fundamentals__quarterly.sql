-- One row per (symbol, fiscal_year, fiscal_quarter) of the quarterly statements, wide, with the
-- date the quarter may be used. The source gives no publication date, so a quarter is usable
-- from its statutory deadline + a buffer (seed fundamental_availability: Circular 96/2020;
-- companies use the whole allowance - v1 measured 99.8 % of 842 announcements within 90 days).
-- Values are the source's FINAL ones: a Q4 figure is the audited one, so the date for Q4 is the
-- audited deadline (90 days), not the 30-day unaudited one.
-- Zero trap: the source writes 0 for an item that does not apply to a company; an item that is
-- 0 in every period of a symbol (`is_item_all_zero`) becomes NULL. v1 decides this per
-- industry; per symbol is stricter and needs no industry join (knowledge: data-sources.md).
-- Operating cash flow is not in the source's cash-flow list; it is derived from the closed
-- identity of the cash-flow statement, as v1 does (knowledge: data-sources.md, fundamentals):
--   operating = change in cash - investing - financing - FX effect,
-- with cash = balance-sheet line 110 (cash and equivalents). The source names that line after
-- the bank template ('Tiền, vàng gửi tại các TCTD khác'); for non-banks it equals cash +
-- equivalents in 100 % of v1's 34,865 checked rows, so it is used alone - adding the two parts
-- as well would count cash twice. Flows are per quarter, not cumulative (v1's measurement).
-- Banks have no 'Tiền' line and get NULL; so does a quarter whose previous quarter is missing.
{%- set items = [
    ('revenue_vnd', 'income_statement', 'Doanh thu thuần HĐKD BH (10=03+04)'),
    ('profit_after_tax_vnd', 'income_statement', 'Lợi nhuận sau thuế (XI-XII)'),
    ('minority_interest_vnd', 'income_statement', 'Lợi ích của cổ đông thiểu số'),
    ('cash_and_equivalents_vnd', 'balance_sheet', 'Tiền, vàng gửi tại các TCTD khác'),
    ('cash_on_hand_vnd', 'balance_sheet', 'Tiền'),
    ('fx_cash_effect_vnd', 'cash_flow', 'Ảnh hưởng của chênh lệch tỷ giá'),
    ('investing_cash_flow_vnd', 'cash_flow', 'Lưu chuyển tiền thuần từ hoạt động đầu tư'),
    ('financing_cash_flow_vnd', 'cash_flow', 'Lưu chuyển tiền thuần từ hoạt động tài chính'),
    ('roe_as_given', 'ratio', 'ROE (%)'),
    ('shares_outstanding', 'ratio', 'numberOfSharesMktCap'),
] %}
with quarterly as (
    select *
    from {{ ref('stg_vnstock__fundamental_statement') }}
    where period_type = 'quarter'
),

wide as (
    select
        symbol,
        fiscal_year,
        fiscal_quarter,
        max(period_end_date) as period_end_date,
        max(v1_available_from_date) as v1_available_from_date,
        {%- for name, statement, key in items %}
        max(
            case
                when statement = '{{ statement }}' and item_key = '{{ key }}' and not is_item_all_zero
                    then value
            end
        ) as {{ name }}{{ ',' if not loop.last }}
        {%- endfor %}
    from quarterly
    group by symbol, fiscal_year, fiscal_quarter
),

with_previous as (
    select
        *,
        fiscal_year * 4 + fiscal_quarter
            - lag(fiscal_year * 4 + fiscal_quarter) over (
                partition by symbol order by fiscal_year, fiscal_quarter
            ) as quarters_since_previous,
        lag(cash_and_equivalents_vnd) over (
            partition by symbol order by fiscal_year, fiscal_quarter
        ) as previous_cash_vnd
    from wide
)

select
    w.symbol,
    w.fiscal_year,
    w.fiscal_quarter,
    w.period_end_date,
    {{ add_days('w.period_end_date', 'a.deadline_days + a.buffer_days') }} as available_from_date,
    w.v1_available_from_date,
    w.revenue_vnd,
    w.profit_after_tax_vnd,
    w.minority_interest_vnd,
    w.profit_after_tax_vnd - coalesce(w.minority_interest_vnd, 0) as parent_profit_vnd,
    case
        when w.quarters_since_previous = 1 and w.cash_on_hand_vnd is not null
            then w.cash_and_equivalents_vnd - w.previous_cash_vnd
                - w.investing_cash_flow_vnd - w.financing_cash_flow_vnd
                - coalesce(w.fx_cash_effect_vnd, 0)
    end as operating_cash_flow_vnd,
    w.roe_as_given,
    w.shares_outstanding
from with_previous as w
inner join {{ ref('fundamental_availability') }} as a
    on a.fiscal_quarter = w.fiscal_quarter
