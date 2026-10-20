-- The date a quarter may be used is one rule written twice: here from the seed
-- fundamental_availability, in v1 as its own available_from_date. Every row must agree; a drift
-- in either copy moves a feature forward in time (look-ahead) or backward (stale data).
select symbol, fiscal_year, fiscal_quarter, available_from_date, v1_available_from_date
from {{ ref('fct_fundamental_quarterly') }}
where v1_available_from_date is null
    or available_from_date != v1_available_from_date
