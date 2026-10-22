-- One row per (as_of_date, group_code, symbol) of the VN30 / HNX30 ledger, with whether the
-- symbol was in the group on the group's previous recorded date (a change is an inclusion or,
-- read from the other side, an exclusion). The first recorded date has no previous one.
with dated as (
    select
        *,
        lag(as_of_date) over (partition by group_code order by as_of_date) as previous_ledger_date
    from (select distinct as_of_date, group_code from {{ ref('stg_vci__index_membership') }}) as d
)

select
    m.as_of_date,
    m.group_code,
    m.symbol,
    d.previous_ledger_date,
    case
        when d.previous_ledger_date is null then null
        else p.symbol is null
    end as is_new_member
from {{ ref('stg_vci__index_membership') }} as m
inner join dated as d
    on d.as_of_date = m.as_of_date and d.group_code = m.group_code
left join {{ ref('stg_vci__index_membership') }} as p
    on p.as_of_date = d.previous_ledger_date
    and p.group_code = m.group_code
    and p.symbol = m.symbol
