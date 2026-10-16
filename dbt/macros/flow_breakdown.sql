{#
  flows.md §2.3: per row and side (buy, sell) and unit (qty, value_vnd), match + put-through
  must equal total. A row is valid when every check holds within `flow_breakdown_tolerance`
  and, when `valid_from` is given (foreign flow), on or after it (earlier rows carried 0 for
  "no data"). An invalid row keeps total and gets NULL match and put-through columns; a NULL
  in any input makes the row invalid. Net is derived as buy minus sell for every kind, so
  its name is its expression. `p` is the column prefix (foreign or prop).
#}
{% macro null_invalid_flow_split(relation, p, valid_from=none) %}
{%- set kinds = ['match', 'put_through', 'total'] -%}
{%- set units = ['qty', 'value_vnd'] -%}
with checked as (
    select
        symbol,
        trade_date,
        {%- for side in ['buy', 'sell'] %}{% for kind in kinds %}{% for unit in units %}
        {{ p }}_{{ side }}_{{ kind }}_{{ unit }},
        {%- endfor %}{% endfor %}{% endfor %}
        is_source_breakdown_valid,
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
),

split as (
    select
        symbol,
        trade_date,
        {%- for side in ['buy', 'sell'] %}{% for unit in units %}
        case when is_breakdown_valid then {{ p }}_{{ side }}_match_{{ unit }} end
            as {{ p }}_{{ side }}_match_{{ unit }},
        case when is_breakdown_valid then {{ p }}_{{ side }}_put_through_{{ unit }} end
            as {{ p }}_{{ side }}_put_through_{{ unit }},
        {{ p }}_{{ side }}_total_{{ unit }},
        {%- endfor %}{% endfor %}
        is_breakdown_valid,
        is_source_breakdown_valid
    from checked
)

select
    symbol,
    trade_date,
    {%- for side in ['buy', 'sell'] %}{% for kind in kinds %}{% for unit in units %}
    {{ p }}_{{ side }}_{{ kind }}_{{ unit }},
    {%- endfor %}{% endfor %}{% endfor %}
    {%- for kind in kinds %}{% for unit in units %}
    {{ p }}_buy_{{ kind }}_{{ unit }} - {{ p }}_sell_{{ kind }}_{{ unit }} as {{ p }}_net_{{ kind }}_{{ unit }},
    {%- endfor %}{% endfor %}
    is_breakdown_valid,
    is_source_breakdown_valid
from split
{% endmacro %}
