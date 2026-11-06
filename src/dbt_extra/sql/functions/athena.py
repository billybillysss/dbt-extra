"""Athena engine 3 gaps; deliberately not inherited from Trino."""

from dbt_extra.sql.functions.models import FunctionSpec as F


FUNCTIONS = (
    F("format_number", "format_number(123456)", "VARCHAR", 1, 1),
    F("contains_sequence", "contains_sequence(ARRAY[1,2,3], ARRAY[1,2])", "BOOLEAN", 2, 2),
    F("murmur3", "murmur3(to_utf8('abc'))", "VARBINARY", 1, 1),
    F("invoker_principal", "invoker_principal()", "VARCHAR", 0, 0, volatility="stable"),
    F("all_match", "all_match(ARRAY[1,2], x -> x > 0)", "BOOLEAN", 2, 2),
    F("any_match", "any_match(ARRAY[1,2], x -> x > 0)", "BOOLEAN", 2, 2),
    F("none_match", "none_match(ARRAY[1,2], x -> x > 0)", "BOOLEAN", 2, 2),
    F("json_size", "json_size('{}', '$')", "BIGINT", 2, 2),
    F("json_array_length", "json_array_length('[1,2]')", "BIGINT", 1, 1),
    F("is_json_scalar", "is_json_scalar('1')", "BOOLEAN", 1, 1),
    F("to_iso8601", "to_iso8601(DATE '2026-01-01')", "VARCHAR", 1, 1),
    F("parse_duration", "parse_duration('5m')", None, 1, 1),
    F("checksum", "checksum(id)", "VARBINARY", 1, 1, "aggregate"),
)
