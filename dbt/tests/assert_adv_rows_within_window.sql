-- v1 dq 14. ADV reads at most `adv_window_rows` previous rows.
-- Fails on: a window wider than configured (e.g. `21 preceding`).
select symbol, trade_date, adv_rows
from {{ ref('fct_liquidity_daily') }}
where adv_rows > {{ var('adv_window_rows') }}
