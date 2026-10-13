{#
  Date functions that differ between warehouses (spec P2: warehouse-specific SQL only
  behind macros). BigQuery is the production target, DuckDB runs the CI unit tests;
  later phases add Snowflake, Athena and Databricks dispatches.
#}

{# Every calendar day from start_date to end_date (inclusive), as column calendar_date. #}
{% macro date_spine_days(start_date, end_date) %}
    {{ return(adapter.dispatch('date_spine_days', 'vnmarket')(start_date, end_date)) }}
{% endmacro %}

{% macro bigquery__date_spine_days(start_date, end_date) %}
    select calendar_date
    from unnest(generate_date_array(date '{{ start_date }}', date '{{ end_date }}')) as calendar_date
{% endmacro %}

{% macro default__date_spine_days(start_date, end_date) %}
    select cast(d as date) as calendar_date
    from generate_series(date '{{ start_date }}', date '{{ end_date }}', interval 1 day) as t(d)
{% endmacro %}

{# True on Monday to Friday. #}
{% macro is_weekday(column) %}
    {{ return(adapter.dispatch('is_weekday', 'vnmarket')(column)) }}
{% endmacro %}

{% macro bigquery__is_weekday(column) %}
    (extract(dayofweek from {{ column }}) not in (1, 7))
{% endmacro %}

{% macro default__is_weekday(column) %}
    (extract(isodow from {{ column }}) < 6)
{% endmacro %}

{# ISO year and week as one integer, e.g. 202642: the key of a trading week. #}
{% macro iso_week_id(column) %}
    {{ return(adapter.dispatch('iso_week_id', 'vnmarket')(column)) }}
{% endmacro %}

{% macro bigquery__iso_week_id(column) %}
    (extract(isoyear from {{ column }}) * 100 + extract(isoweek from {{ column }}))
{% endmacro %}

{% macro default__iso_week_id(column) %}
    (extract(isoyear from {{ column }}) * 100 + extract(week from {{ column }}))
{% endmacro %}
