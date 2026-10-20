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

{# ISO weekday: 1 = Monday ... 7 = Sunday (BI v3: the calendar heat strip's columns). #}
{% macro iso_weekday(column) %}
    {{ return(adapter.dispatch('iso_weekday', 'vnmarket')(column)) }}
{% endmacro %}

{% macro bigquery__iso_weekday(column) %}
    (mod(extract(dayofweek from {{ column }}) + 5, 7) + 1)
{% endmacro %}

{% macro default__iso_weekday(column) %}
    extract(isodow from {{ column }})
{% endmacro %}

{# The Monday of the ISO week holding the date (BI v3: weekly matrix headers). #}
{% macro iso_week_start(column) %}
    {{ return(adapter.dispatch('iso_week_start', 'vnmarket')(column)) }}
{% endmacro %}

{% macro bigquery__iso_week_start(column) %}
    date_trunc({{ column }}, isoweek)
{% endmacro %}

{% macro default__iso_week_start(column) %}
    cast(date_trunc('week', {{ column }}) as date)
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

{# The exact median of `column` within `partition_by`, as a window (an aggregate median is
   approximate or absent on BigQuery). Wrap with max() in a later group by. #}
{% macro median_over(column, partition_by) %}
    {{ return(adapter.dispatch('median_over', 'vnmarket')(column, partition_by)) }}
{% endmacro %}

{% macro bigquery__median_over(column, partition_by) %}
    percentile_cont({{ column }}, 0.5) over (partition by {{ partition_by }})
{% endmacro %}

{% macro default__median_over(column, partition_by) %}
    median({{ column }}) over (partition by {{ partition_by }})
{% endmacro %}
