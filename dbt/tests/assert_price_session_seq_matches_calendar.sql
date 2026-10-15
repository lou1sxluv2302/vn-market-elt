-- v1 dq 6. A price row's session_seq is the calendar's for its date.
-- Fails on: a sequence counted per symbol (row_number) instead of per market session, which
-- agrees with the calendar only for symbols that traded from the first session on.
select p.symbol, p.trade_date, p.session_seq, c.session_seq as calendar_session_seq
from {{ ref('fct_price_daily') }} as p
join {{ ref('dim_trading_calendar') }} as c on c.calendar_date = p.trade_date
where p.session_seq is distinct from c.session_seq
