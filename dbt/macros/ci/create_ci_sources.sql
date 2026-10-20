{#
  CI only (DuckDB): create empty source tables with the real column types, so
  unit tests can introspect their parents. Never runs against BigQuery.
  Usage: dbt run-operation create_ci_sources --target ci
#}
{% macro create_ci_sources() %}
    {% if target.type != 'duckdb' %}
        {{ exceptions.raise_compiler_error("create_ci_sources is for the DuckDB CI target only") }}
    {% endif %}
    {% set ddl %}
        create schema if not exists raw_vnstock;
        create table if not exists raw_vnstock.ohlcv_daily (
            symbol varchar, session_date date,
            open_vnd bigint, high_vnd bigint, low_vnd bigint, close_vnd bigint, volume bigint,
            _source_id varchar, _batch_id varchar, _ingested_at timestamptz, _payload_hash varchar,
            _source_file varchar, _ingest_partition date
        );
        create table if not exists raw_vnstock.ref_symbols_by_exchange (
            symbol varchar, exchange varchar, type varchar, sid double, organ_short_name varchar,
            organ_name varchar, product_grp_id varchar, icb_code2 varchar,
            _source_sha256 varchar, _loaded_at timestamptz
        );
        {%- for prefix, table in [('fr', 'foreign_trade_daily'), ('prop', 'prop_trade_daily')] %}
        create table if not exists raw_vnstock.{{ table }} (
            symbol varchar, session_date date,
            {%- for side in ['buy', 'sell', 'net'] %}{% for unit in ['vol', 'val'] %}{% for src in ['matched', 'deal', 'total'] %}
            {{ prefix }}_{{ side }}_{{ unit }}_{{ src }} double,
            {%- endfor %}{% endfor %}{% endfor %}
            breakdown_valid boolean, source varchar,
            _source_sha256 varchar, _loaded_at timestamptz
        );
        {%- endfor %}
        create table if not exists raw_vnstock.ref_symbols_by_industries (
            symbol varchar, organ_name varchar, com_type_code varchar, icb_level bigint,
            icb_code varchar, icb_name varchar, _source_sha256 varchar, _loaded_at timestamptz
        );
        create table if not exists raw_vnstock.ref_industries_icb (
            icb_name varchar, en_icb_name varchar, icb_code varchar, level bigint,
            _source_sha256 varchar, _loaded_at timestamptz
        );
        create table if not exists raw_vnstock.fundamental_statement (
            symbol varchar, statement varchar, item varchar, lan_xuat_hien bigint,
            period_type varchar, period_label varchar, year bigint, quarter double, value double,
            item_key varchar, is_meta boolean, dup_item_label boolean, dup_period_col boolean,
            period_end_date date, available_from_date date, item_all_zero boolean,
            item_all_null boolean, src varchar, loaded_at timestamptz,
            _source_sha256 varchar, _loaded_at timestamptz
        );
        create table if not exists raw_vnstock.index_daily (
            index_code varchar, session_date date,
            open double, high double, low double, close double, volume bigint, _source_id varchar,
            _source_sha256 varchar, _loaded_at timestamptz
        );
    {% endset %}
    {% do run_query(ddl) %}
    {{ log("CI source tables created", info=True) }}
{% endmacro %}
