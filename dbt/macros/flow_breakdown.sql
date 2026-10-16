{#
  flows.md §2.3: per row and side (buy, sell) and unit (qty, value_vnd), match + put-through
  must equal total. A row is valid when every check holds within `flow_breakdown_tolerance`,
  and, for foreign flow, on or after `foreign_breakdown_valid_from` (earlier rows carried 0
  for "no data"). An invalid row keeps total and gets NULL match and put-through columns.
  `p` is the column prefix (foreign or prop); `relation` a staging model.
#}
{% macro flow_with_breakdown(relation, p, valid_from=none) %}
{%- set sides = ['buy', 'sell', 'net'] -%}
{%- set units = ['qty', 'value_vnd'] -%}
with checked as (
    select
        *,
        coalesce(
            {%- for side in ['buy', 'sell'] %}{% for unit in units %}
            abs({{ p }}_{{ side }}_match_{{ unit }} + {{ p }}_{{ side }}_put_through_{{ unit }}
                - {{ p }}_{{ side }}_total_{{ unit }}) <= {{ var('flow_breakdown_tolerance') }}
            {%- if not loop.last %} and{% endif %}{% endfor %}{% if not loop.last %} and{% endif %}
            {%- endfor %}
            {%- if valid_from %}
            and trade_date >= cast('{{ valid_from }}' as date)
            {%- endif %},
            false
        ) as is_breakdown_valid
    from {{ relation }}
)

select
    symbol,
    trade_date,
    {%- for side in sides %}{% for unit in units %}
    case when is_breakdown_valid then {{ p }}_{{ side }}_match_{{ unit }} end
        as {{ p }}_{{ side }}_match_{{ unit }},
    case when is_breakdown_valid then {{ p }}_{{ side }}_put_through_{{ unit }} end
        as {{ p }}_{{ side }}_put_through_{{ unit }},
    {{ p }}_{{ side }}_total_{{ unit }},
    {%- endfor %}{% endfor %}
    is_breakdown_valid,
    is_source_breakdown_valid
from checked
{% endmacro %}
