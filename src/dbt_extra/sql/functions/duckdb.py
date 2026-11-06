"""DuckDB gaps in SQLGlot 30.29.0.

Source: https://duckdb.org/docs/2.0/sql/functions/utility.html
CLI-only getenv is deliberately excluded. Settings and version-dependent stats
types stay unresolved; error always raises. No calls are executed for inference.
"""

from dbt_extra.sql.functions.models import FunctionSpec as F


FUNCTIONS = (
    F("current_setting", "current_setting('threads')", None, 1, 1, volatility="stable"),
    F("pg_typeof", "pg_typeof(id)", "VARCHAR", 1, 1),
    F("stats", "stats(id)", None, 1, 1, volatility="stable"),
    F("error", "error('stop')", None, 1, 1, volatility="volatile"),
    F("list_sum", "list_sum([1,2])", None, 1, 1),
    F("list_avg", "list_avg([1,2])", "DOUBLE", 1, 1),
    F("list_reduce", "list_reduce([1,2], (x,y) -> x+y)", None, 2, 3),
    F("list_zip", "list_zip([1,2], [3,4])", None, 1, None),
    F("list_grade_up", "list_grade_up([2,1])", "BIGINT[]", 1, 3),
    F("json_valid", "json_valid('{}')", "BOOLEAN", 1, 1),
    F("json_structure", "json_structure('{}')", "JSON", 1, 1),
    F("json_contains", "json_contains('{\"a\":1}', '1')", "BOOLEAN", 2, 2),
    F("json_array_length", "json_array_length('[1,2]')", None, 1, 2),
    F("json_transform", "json_transform('{\"a\":1}', '{\"a\":\"INTEGER\"}')", None, 2, 2),
    F("json_group_array", "json_group_array(id)", "JSON", 1, 1, "aggregate"),
    F("json_group_object", "json_group_object('a', id)", "JSON", 2, 2, "aggregate"),
    F("json_group_structure", "json_group_structure('{}')", "JSON", 1, 1, "aggregate"),
    F("regexp_escape", "regexp_escape('a.b')", "VARCHAR", 1, 1),
    F("can_cast_implicitly", "can_cast_implicitly(1, 1::BIGINT)", "BOOLEAN", 2, 2),
    F("create_sort_key", "create_sort_key(id, 'ASC NULLS FIRST')", None, 2, None),
    F("current_query", "current_query()", "VARCHAR", 0, 0, volatility="stable"),
    F("nextval", "nextval('seq')", "BIGINT", 1, 1, volatility="volatile"),
    F("setseed", "setseed(0.5)", None, 1, 1, volatility="volatile"),
    F("txid_current", "txid_current()", "UBIGINT", 0, 0, volatility="volatile"),
)
