"""Snowflake Anonymous gaps; context access never grants rewrite permission."""

from dbt_extra.sql.functions.models import FunctionSpec as F


FUNCTIONS = (
    F("get_ddl", "get_ddl('TABLE', 't')", "VARCHAR", 2, 3, volatility="stable"),
    F("last_query_id", "last_query_id()", "VARCHAR", 0, 1, volatility="volatile"),
    F("is_role_in_session", "is_role_in_session('PUBLIC')", "BOOLEAN", 1, 1, volatility="stable"),
    F("is_database_role_in_session", "is_database_role_in_session('reader')", "BOOLEAN", 1, 1, volatility="stable"),
    F("is_object", "is_object(parse_json('{}'))", "BOOLEAN", 1, 1),
    F("is_boolean", "is_boolean(parse_json('true'))", "BOOLEAN", 1, 1),
    F("is_integer", "is_integer(parse_json('1'))", "BOOLEAN", 1, 1),
    F("is_decimal", "is_decimal(parse_json('1.5'))", "BOOLEAN", 1, 1),
    F("is_double", "is_double(parse_json('1.5'))", "BOOLEAN", 1, 1),
    F("is_date_value", "is_date_value(to_variant(DATE '2026-01-01'))", "BOOLEAN", 1, 1),
    F("is_timestamp_ntz", "is_timestamp_ntz(to_variant(TIMESTAMP_NTZ '2026-01-01'))", "BOOLEAN", 1, 1),
    F("object_pick", "object_pick(parse_json('{}'), 'a')", None, 2, None),
    F("object_delete", "object_delete(parse_json('{}'), 'a')", None, 2, None),
    F("hll_estimate", "hll_estimate(CAST(NULL AS BINARY))", None, 1, 1, "aggregate"),
    F("hash", "hash(id)", "NUMBER(19,0)", 1, None),
    F("result_scan", "result_scan(last_query_id())", None, 0, 1, "generator", volatility="volatile"),
)
