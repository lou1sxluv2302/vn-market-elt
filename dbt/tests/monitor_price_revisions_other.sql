-- P4 (Q1). Vendor rewrites that are neither a restated session, a corporate-action rescale
-- nor rounding noise, above the count measured when the classes were set
-- (`revision_other_ceiling`). A warning: a rewrite is a fact about the source, not a fault
-- in the data, and staging already keeps the newest pull. Read fct_price_revision for it.
{{ config(severity='warn') }}
select count(*) as other_revisions
from {{ ref('fct_price_revision') }}
where revision_class = 'other'
having count(*) > {{ var('revision_other_ceiling') }}
