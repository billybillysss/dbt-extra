"""Trino Anonymous gaps, including disjoint BAR overloads."""

from dbt_extra.sql.functions.models import FunctionSpec as F


FUNCTIONS = (
    F("bar", "bar(0.5, 10)", "VARCHAR", 2, 4, arities=(2, 4)),
    F("human_readable_seconds", "human_readable_seconds(3600)", "VARCHAR", 1, 1),
    F("contains_sequence", "contains_sequence(ARRAY[1,2,3], ARRAY[1,2])", "BOOLEAN", 2, 2),
    F("murmur3", "murmur3(to_utf8('abc'))", "VARBINARY", 1, 1),
    F("array_histogram", "array_histogram(ARRAY[1,2])", None, 1, 1),
    F("all_match", "all_match(ARRAY[1,2], x -> x > 0)", "BOOLEAN", 2, 2),
    F("any_match", "any_match(ARRAY[1,2], x -> x > 0)", "BOOLEAN", 2, 2),
    F("none_match", "none_match(ARRAY[1,2], x -> x > 0)", "BOOLEAN", 2, 2),
    F("map_filter", "map_filter(MAP(ARRAY['a'], ARRAY[1]), (k,v) -> v > 0)", None, 2, 2),
    F("map_zip_with", "map_zip_with(MAP(ARRAY['a'], ARRAY[1]), MAP(ARRAY['a'], ARRAY[2]), (k,v1,v2) -> v1+v2)", None, 3, 3),
    F("zip_with", "zip_with(ARRAY[1], ARRAY[2], (x,y) -> x+y)", None, 3, 3),
    F("json_size", "json_size('{}', '$')", "BIGINT", 2, 2),
    F("json_array_length", "json_array_length('[1,2]')", "BIGINT", 1, 1),
    F("is_json_scalar", "is_json_scalar('1')", "BOOLEAN", 1, 1),
    F("luhn_check", "luhn_check('79927398713')", "BOOLEAN", 1, 1),
    F("format_number", "format_number(123456)", "VARCHAR", 1, 1),
    F("to_iso8601", "to_iso8601(DATE '2026-01-01')", "VARCHAR", 1, 1),
    F("parse_duration", "parse_duration('5m')", None, 1, 1),
    F("checksum", "checksum(id)", "VARBINARY", 1, 1, "aggregate"),
    F("numeric_histogram", "numeric_histogram(5, id)", None, 2, 3, "aggregate"),
    F("approx_most_frequent", "approx_most_frequent(2, id, 10)", None, 3, 3, "aggregate"),
)
