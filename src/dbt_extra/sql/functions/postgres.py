"""PostgreSQL 18 gaps in SQLGlot 30.29.0.

Sources: https://www.postgresql.org/docs/18/functions-info.html,
functions-admin.html and functions-json.html. regtype is not assumed to be TEXT.
Context-sensitive and session-mutating calls remain evaluation barriers.
"""

from dbt_extra.sql.functions.models import FunctionSpec as F


FUNCTIONS = (
    F("pg_typeof", "pg_typeof(id)", None, 1, 1),
    F("current_setting", "current_setting('search_path')", "TEXT", 1, 2, volatility="stable"),
    F("set_config", "set_config('search_path', 'public', false)", "TEXT", 3, 3, volatility="volatile"),
    F("pg_backend_pid", "pg_backend_pid()", "INTEGER", 0, 0, volatility="stable"),
    F("pg_is_in_recovery", "pg_is_in_recovery()", "BOOLEAN", 0, 0, volatility="volatile"),
    F("jsonb_path_exists", "jsonb_path_exists('{}'::jsonb, '$.a')", "BOOLEAN", 2, 4),
    F("jsonb_array_length", "jsonb_array_length('[1,2]'::jsonb)", "INTEGER", 1, 1),
    F("jsonb_typeof", "jsonb_typeof('{}'::jsonb)", "TEXT", 1, 1),
    F("jsonb_pretty", "jsonb_pretty('{}'::jsonb)", "TEXT", 1, 1),
    F("jsonb_strip_nulls", "jsonb_strip_nulls('{}'::jsonb)", "JSONB", 1, 2),
    F("jsonb_set", "jsonb_set('{}'::jsonb, ARRAY['a'], '1'::jsonb)", "JSONB", 3, 4),
    F("jsonb_insert", "jsonb_insert('{}'::jsonb, ARRAY['a'], '1'::jsonb)", "JSONB", 3, 4),
    F("jsonb_path_query_first", "jsonb_path_query_first('{}'::jsonb, '$.a')", "JSONB", 2, 4),
    F("jsonb_path_match", "jsonb_path_match('{}'::jsonb, 'exists($.a)')", "BOOLEAN", 2, 4),
    F("jsonb_path_query", "jsonb_path_query('{}'::jsonb, '$.a')", None, 2, 4, "generator"),
    F("jsonb_each", "jsonb_each('{}'::jsonb)", None, 1, 1, "generator"),
    F("array_ndims", "array_ndims(ARRAY[1,2])", "INTEGER", 1, 1),
    F("array_dims", "array_dims(ARRAY[1,2])", "TEXT", 1, 1),
    F("array_positions", "array_positions(ARRAY[1,2], 2)", "INTEGER[]", 2, 2),
    F("array_sample", "array_sample(ARRAY[1,2], 1)", None, 2, 2, volatility="volatile"),
    F("array_shuffle", "array_shuffle(ARRAY[1,2])", None, 1, 1, volatility="volatile"),
    F("cardinality", "cardinality(ARRAY[1,2])", "INTEGER", 1, 1),
    F("num_nonnulls", "num_nonnulls(id, NULL)", "INTEGER", 1, None),
    F("num_nulls", "num_nulls(id, NULL)", "INTEGER", 1, None),
    F("pg_column_size", "pg_column_size(id)", "INTEGER", 1, 1),
    F("pg_size_pretty", "pg_size_pretty(id)", "TEXT", 1, 1),
    F("clock_timestamp", "clock_timestamp()", "TIMESTAMPTZ", 0, 0, volatility="volatile"),
    F("statement_timestamp", "statement_timestamp()", "TIMESTAMPTZ", 0, 0, volatility="stable"),
    F("transaction_timestamp", "transaction_timestamp()", "TIMESTAMPTZ", 0, 0, volatility="stable"),
    F("timeofday", "timeofday()", "TEXT", 0, 0, volatility="volatile"),
    F("txid_current", "txid_current()", "BIGINT", 0, 0, volatility="volatile"),
    F("nextval", "nextval('seq')", "BIGINT", 1, 1, volatility="volatile"),
    F("setval", "setval('seq', 1)", "BIGINT", 2, 3, volatility="volatile"),
    F("pg_notify", "pg_notify('channel', 'message')", None, 2, 2, volatility="volatile"),
    F("pg_sleep", "pg_sleep(0)", None, 1, 1, volatility="volatile"),
    F("uuidv7", "uuidv7()", "UUID", 0, 1, volatility="volatile"),
)
