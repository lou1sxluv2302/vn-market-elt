{#
  on-run-end (BI plan B2): after every prod invocation, one row in marts_daily.fct_build_status
  - when, the last observed session (`as_of_date`), and how the invocation's nodes ended. The
  BI report shows the newest row on every page as its `as_of` and data-quality state
  (bi-conventions §5). Prod only: the CI and dev targets never write it. Append-only.
#}
{% macro record_build_status(results) %}
  {% if execute and target.name == 'prod' %}
    {% set counts = {'models_ok': 0, 'tests_passed': 0, 'tests_warned': 0, 'tests_failed': 0, 'nodes_errored': 0, 'nodes_skipped': 0} %}
    {% for r in results %}
      {% set kind = r.node.resource_type %}
      {% if r.status == 'error' %}
        {% do counts.update({'nodes_errored': counts['nodes_errored'] + 1}) %}
      {% elif r.status == 'skipped' %}
        {% do counts.update({'nodes_skipped': counts['nodes_skipped'] + 1}) %}
      {% elif kind == 'test' and r.status == 'pass' %}
        {% do counts.update({'tests_passed': counts['tests_passed'] + 1}) %}
      {% elif kind == 'test' and r.status == 'warn' %}
        {% do counts.update({'tests_warned': counts['tests_warned'] + 1}) %}
      {% elif kind == 'test' and r.status == 'fail' %}
        {% do counts.update({'tests_failed': counts['tests_failed'] + 1}) %}
      {% elif kind == 'model' and r.status == 'success' %}
        {% do counts.update({'models_ok': counts['models_ok'] + 1}) %}
      {% endif %}
    {% endfor %}
    {% set dataset = target.database ~ '.' ~ var('build_status_dataset') %}
    {% set sql %}
      create table if not exists `{{ dataset }}.fct_build_status` (
        built_at timestamp,
        invocation_id string,
        command string,
        as_of_date date,
        models_ok int64,
        tests_passed int64,
        tests_warned int64,
        tests_failed int64,
        nodes_errored int64,
        nodes_skipped int64
      );
      insert into `{{ dataset }}.fct_build_status`
      select
        current_timestamp(),
        '{{ invocation_id }}',
        '{{ flags.WHICH }}',
        (
          select max(calendar_date)
          from `{{ dataset }}.dim_trading_calendar`
          where calendar_source = 'observed' and is_trading_day
        ),
        {{ counts['models_ok'] }}, {{ counts['tests_passed'] }}, {{ counts['tests_warned'] }},
        {{ counts['tests_failed'] }}, {{ counts['nodes_errored'] }}, {{ counts['nodes_skipped'] }};
    {% endset %}
    {% do run_query(sql) %}
  {% endif %}
{% endmacro %}
