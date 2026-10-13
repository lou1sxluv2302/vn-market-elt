{#
  v1's bad-row rules for one price row, in one place: int_prices__flagged reports them,
  int_prices__chosen_source uses them to prefer a clean row over the primary source.
  `p` is the row alias (empty string for an unqualified row).
#}
{% macro is_bad_null(p='') %}
    ({{ p }}close_vnd is null or {{ p }}open_vnd is null
     or {{ p }}high_vnd is null or {{ p }}low_vnd is null)
{% endmacro %}

{% macro is_bad_nonpositive(p='') %}
    ({{ p }}close_vnd <= 0)
{% endmacro %}

{% macro is_bad_ohlc(p='') %}
    -- low > high is implied by the other two terms; kept so the formula reads as v1's.
    ({{ p }}low_vnd > {{ p }}high_vnd or {{ p }}close_vnd < {{ p }}low_vnd
     or {{ p }}close_vnd > {{ p }}high_vnd)
{% endmacro %}

{# True when any of the three structural checks fails or cannot be evaluated. #}
{% macro is_broken_row(p='') %}
    coalesce({{ is_bad_null(p) }} or {{ is_bad_nonpositive(p) }} or {{ is_bad_ohlc(p) }}, true)
{% endmacro %}
