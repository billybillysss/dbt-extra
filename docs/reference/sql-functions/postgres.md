# PostgreSQL SQL functions

## dbt-extra local function gaps

These entries fill SQLGlot 30.29.0 Anonymous-function gaps, reviewed against
PostgreSQL 18 sources: [information functions](https://www.postgresql.org/docs/18/functions-info.html),
[administration functions](https://www.postgresql.org/docs/18/functions-admin.html),
and [JSON functions](https://www.postgresql.org/docs/18/functions-json.html).

`pg_typeof` accepts one argument and returns `regtype`, an OID alias—not TEXT;
its type stays unresolved. `current_setting` accepts one or two arguments and
returns TEXT. `set_config` takes three and returns TEXT but mutates session state.
`pg_backend_pid` and `pg_is_in_recovery` take no arguments. `jsonb_path_exists`
takes two to four arguments (target, path, optional variables and silent flag).
Native `generate_series` remains outside this catalog, including its generator
and overload semantics.

`stable` means context-dependent; `volatile` includes session mutation and state
that may change during execution. Every local call remains an error/evaluation
rewrite barrier, including immutable ones. No session changes or function
evaluations are performed during inference or enrichment.

See [contracts and enrichment examples](README.md), the
[catalog](../../../src/dbt_extra/sql/functions/postgres.py), and
[tests](../../../tests/sql/functions/test_postgres.py). Verification is offline,
not PostgreSQL server execution certification.

The expanded PostgreSQL 18 set includes explicit
[array](https://www.postgresql.org/docs/18/functions-array.html),
[JSON](https://www.postgresql.org/docs/18/functions-json.html), size, clock,
sequence and notification contracts. `array_positions` returns INTEGER[], not
the element type; random sampling/shuffling remains input-dependent and volatile.
`jsonb_each` and `jsonb_path_query` are set-returning boundaries. The two-argument
`jsonb_strip_nulls` and `uuidv7` contracts are PostgreSQL-18-specific.
`clock_timestamp`/`timeofday` may change within a statement; statement/transaction
timestamps are stable observations, not immutable constants. No stateful call is executed.
Native `generate_series` is also treated as set-returning, unlike DuckDB's scalar list.

| Function | Kind | Return type policy | Volatility |
| --- | --- | --- | --- |
| `pg_typeof` | scalar | unresolved / input-dependent | immutable |
| `current_setting` | scalar | `TEXT` | stable |
| `set_config` | scalar | `TEXT` | volatile |
| `pg_backend_pid` | scalar | `INTEGER` | stable |
| `pg_is_in_recovery` | scalar | `BOOLEAN` | volatile |
| `jsonb_path_exists` | scalar | `BOOLEAN` | immutable |
| `jsonb_array_length` | scalar | `INTEGER` | immutable |
| `jsonb_typeof` | scalar | `TEXT` | immutable |
| `jsonb_pretty` | scalar | `TEXT` | immutable |
| `jsonb_strip_nulls` | scalar | `JSONB` | immutable |
| `jsonb_set` | scalar | `JSONB` | immutable |
| `jsonb_insert` | scalar | `JSONB` | immutable |
| `jsonb_path_query_first` | scalar | `JSONB` | immutable |
| `jsonb_path_match` | scalar | `BOOLEAN` | immutable |
| `jsonb_path_query` | generator | unresolved / input-dependent | immutable |
| `jsonb_each` | generator | unresolved / input-dependent | immutable |
| `array_ndims` | scalar | `INTEGER` | immutable |
| `array_dims` | scalar | `TEXT` | immutable |
| `array_positions` | scalar | `INTEGER[]` | immutable |
| `array_sample` | scalar | unresolved / input-dependent | volatile |
| `array_shuffle` | scalar | unresolved / input-dependent | volatile |
| `cardinality` | scalar | `INTEGER` | immutable |
| `num_nonnulls` | scalar | `INTEGER` | immutable |
| `num_nulls` | scalar | `INTEGER` | immutable |
| `pg_column_size` | scalar | `INTEGER` | immutable |
| `pg_size_pretty` | scalar | `TEXT` | immutable |
| `clock_timestamp` | scalar | `TIMESTAMPTZ` | volatile |
| `statement_timestamp` | scalar | `TIMESTAMPTZ` | stable |
| `transaction_timestamp` | scalar | `TIMESTAMPTZ` | stable |
| `timeofday` | scalar | `TEXT` | volatile |
| `txid_current` | scalar | `BIGINT` | volatile |
| `nextval` | scalar | `BIGINT` | volatile |
| `setval` | scalar | `BIGINT` | volatile |
| `pg_notify` | scalar | unresolved / input-dependent | volatile |
| `pg_sleep` | scalar | unresolved / input-dependent | volatile |
| `uuidv7` | scalar | `UUID` | volatile |

<!-- BEGIN GENERATED FUNCTION INVENTORY -->
## Function implementation reference

All function names and implementation symbols are in the single
[function implementation matrix](README.md#function-implementation-matrix).

Source scope: PostgreSQL 18, Functions and Operators chapter.
See the [official-source snapshot](function_sources.json) for all source URLs (collected 2026-11-05).
<!-- END GENERATED FUNCTION INVENTORY -->
