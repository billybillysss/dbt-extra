"""Redshift gaps verified independently of PostgreSQL parser ancestry."""

from dbt_extra.sql.functions.models import FunctionSpec as F


FUNCTIONS = (
    F("fnv_hash", "fnv_hash('abc')", "BIGINT", 1, 2),
    F("can_json_parse", "can_json_parse('{}')", "BOOLEAN", 1, 1),
    F("json_typeof", "json_typeof(json_parse('{}'))", "VARCHAR", 1, 1),
    F("pg_last_query_id", "pg_last_query_id()", "INTEGER", 0, 0, volatility="volatile"),
    F("json_array_length", "json_array_length('[1,2]')", "INTEGER", 1, 2),
    F("is_valid_json", "is_valid_json('{}')", "BOOLEAN", 1, 1),
    F("is_valid_json_array", "is_valid_json_array('[]')", "BOOLEAN", 1, 1),
    F("json_extract_array_element_text", "json_extract_array_element_text('[1]', 0)", "VARCHAR", 2, 3),
    F("json_serialize", "json_serialize(json_parse('{}'))", "VARCHAR", 1, 1),
    F("json_serialize_to_varbyte", "json_serialize_to_varbyte(json_parse('{}'))", "VARBYTE", 1, 1),
    F("json_size", "json_size(json_parse('{}'))", "INTEGER", 1, 1),
    F("is_object", "is_object(json_parse('{}'))", "BOOLEAN", 1, 1),
    F("is_boolean", "is_boolean(json_parse('true'))", "BOOLEAN", 1, 1),
    F("is_integer", "is_integer(json_parse('1'))", "BOOLEAN", 1, 1),
    F("is_float", "is_float(json_parse('1.5'))", "BOOLEAN", 1, 1),
    F("is_decimal", "is_decimal(json_parse('1.5'))", "BOOLEAN", 1, 1),
    F("is_varchar", "is_varchar(json_parse('\"a\"'))", "BOOLEAN", 1, 1),
    F("get_array_length", "get_array_length(json_parse('[1,2]'))", "INTEGER", 1, 1),
    F("array_flatten", "array_flatten(json_parse('[[1]]'))", "SUPER", 1, 1),
    F("subarray", "subarray(json_parse('[1,2]'), 0, 1)", "SUPER", 3, 3),
)
