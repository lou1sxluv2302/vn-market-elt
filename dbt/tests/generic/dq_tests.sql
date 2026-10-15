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
