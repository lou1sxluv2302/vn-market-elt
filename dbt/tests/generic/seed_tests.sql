{# A combination of columns is unique (written here so the project needs no package). #}
{% test unique_combination(model, columns) %}
    select {{ columns | join(', ') }}, count(*) as n
    from {{ model }}
    group by {{ columns | join(', ') }}
    having count(*) > 1
{% endtest %}

{# A rule table is stale when its newest as_of is older than `days` (one quarter by default);
   an empty table fails too - a check over nothing proves nothing. "Today" is the warehouse's
   UTC date, at most one day off Vietnam time, which does not matter at a 92-day horizon. #}
{% test as_of_within_days(model, days=92) %}
    select max(as_of) as newest_as_of
    from {{ model }}
    having max(as_of) is null
        or max(as_of) < cast({{ dbt.dateadd("day", -days, dbt.current_timestamp()) }} as date)
{% endtest %}
