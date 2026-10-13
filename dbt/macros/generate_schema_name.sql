{#
  One dataset per layer (spec §13.4): prod writes `staging`, `intermediate`,
  `marts_daily`; every other target prefixes them with `dev_` (7-day tables).
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- elif target.name == 'prod' -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        dev_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
