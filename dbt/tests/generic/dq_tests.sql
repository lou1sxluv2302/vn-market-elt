{# An empty model fails: every other test passes on zero rows, so emptiness must be its own
   failure (data-quality-lessons §27). Fails on: a load that wrote nothing. #}
{% test not_empty(model) %}
    select 1 as is_empty
    from (select count(*) as n from {{ model }}) as counted
    where n = 0
{% endtest %}

{# Every row satisfies one condition; the failing rows are returned. One condition per
   instance (data-quality-lessons §28). A null result passes: nulls are not_null's job,
   so one null does not turn several tests red. #}
{% test row_condition(model, condition) %}
    select 1 as broken_row
    from {{ model }}
    where not ({{ condition }})
{% endtest %}

{# flows.md §2.3: on a row whose split is valid, match + put-through = total for every side
   and unit, within `flow_breakdown_tolerance`. Fails on: invalid rows marked valid. #}
{% test breakdown_identity_holds(model, prefix) %}
    select symbol, trade_date
    from {{ model }}
    where is_breakdown_valid
        and not (
            {%- for side in ['buy', 'sell'] %}{% for unit in ['qty', 'value_vnd'] %}
            abs({{ prefix }}_{{ side }}_match_{{ unit }} + {{ prefix }}_{{ side }}_put_through_{{ unit }}
                - {{ prefix }}_{{ side }}_total_{{ unit }}) <= {{ var('flow_breakdown_tolerance') }}
            {%- if not loop.last %} and{% endif %}{% endfor %}{% if not loop.last %} and{% endif %}
            {%- endfor %}
        )
{% endtest %}

{# flows.md §2.3: a row whose split is invalid shows no match or put-through value (they
   would read as real zeros). Fails on: the split kept on an invalid row. #}
{% test split_null_when_invalid(model, prefix) %}
    select symbol, trade_date
    from {{ model }}
    where not is_breakdown_valid
        and coalesce(
            {%- for side in ['buy', 'sell', 'net'] %}{% for kind in ['match', 'put_through'] %}{% for unit in ['qty', 'value_vnd'] %}
            {{ prefix }}_{{ side }}_{{ kind }}_{{ unit }}{% if not loop.last %},{% endif %}
            {%- endfor %}{% if not loop.last %},{% endif %}{% endfor %}{% if not loop.last %},{% endif %}
            {%- endfor %}
        ) is not null
{% endtest %}
