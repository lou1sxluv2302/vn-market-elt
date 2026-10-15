-- v1 validate_all B. Trading days are numbered 1..n with no gap.
-- Fails on: a sequence counted over every calendar day instead of over trading days.
-- Three conditions, one fix (the numbering): starts at 1, ends at the count, none null.
select count(*) as trading_days, min(session_seq) as first_seq, max(session_seq) as last_seq
from {{ ref('dim_trading_calendar') }}
where is_trading_day
having min(session_seq) <> 1 or max(session_seq) <> count(*) or count(session_seq) <> count(*)
