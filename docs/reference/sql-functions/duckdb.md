# DuckDB SQL functions

## dbt-extra local function gaps

These entries fill SQLGlot 30.29.0 Anonymous-function gaps. Source: DuckDB
[utility functions](https://duckdb.org/docs/2.0/sql/functions/utility.html).

Each accepts exactly one argument. `pg_typeof` returns VARCHAR, unlike PostgreSQL's
`regtype`. `current_setting` depends on the setting, so no universal string type
is claimed. `stats` has a version-dependent result (VARIANT in DuckDB 2.0), kept
unresolved across versions. `error` always raises and has no successful value type.
CLI-only `getenv` is deliberately excluded from this local recognition catalog.
Native `list_transform` is not replaced to compensate for lambda/type-inference gaps.

`stable` marks context-sensitive results and `volatile` conservatively marks
`error`. All local entries retain error/evaluation rewrite barriers. Inference
does not read settings, execute queries, or trigger errors.

See [contracts and enrichment examples](README.md), the
[catalog](../../../src/dbt_extra/sql/functions/duckdb.py), and
[tests](../../../tests/sql/functions/test_duckdb.py). This catalog's per-function
checks are offline and separate from the project's DuckDB execution tests.

Additional [list](https://duckdb.org/docs/2.0/sql/functions/list.html),
[JSON](https://duckdb.org/docs/2.0/data/json/json_functions.html) and utility gaps
are registered independently. JSON path-list overloads and list/schema-derived
results stay unresolved when there is no single fixed type. JSON grouping macros
are aggregates, while `list_sum`/`list_avg` are scalar list operations. `create_sort_key`
can bind compact keys differently and therefore has no guessed fixed return type.
Sequence and transaction-state calls are barriers. The installed DuckDB binder
additionally checks supported scalar and numeric native-return repairs offline.

| Function | Kind | Return type policy | Volatility |
| --- | --- | --- | --- |
| `current_setting` | scalar | unresolved / input-dependent | stable |
| `pg_typeof` | scalar | `VARCHAR` | immutable |
| `stats` | scalar | unresolved / input-dependent | stable |
| `error` | scalar | unresolved / input-dependent | volatile |
| `list_sum` | scalar | unresolved / input-dependent | immutable |
| `list_avg` | scalar | `DOUBLE` | immutable |
| `list_reduce` | scalar | unresolved / input-dependent | immutable |
| `list_zip` | scalar | unresolved / input-dependent | immutable |
| `list_grade_up` | scalar | `BIGINT[]` | immutable |
| `json_valid` | scalar | `BOOLEAN` | immutable |
| `json_structure` | scalar | `JSON` | immutable |
| `json_contains` | scalar | `BOOLEAN` | immutable |
| `json_array_length` | scalar | unresolved / input-dependent | immutable |
| `json_transform` | scalar | unresolved / input-dependent | immutable |
| `json_group_array` | aggregate | `JSON` | immutable |
| `json_group_object` | aggregate | `JSON` | immutable |
| `json_group_structure` | aggregate | `JSON` | immutable |
| `regexp_escape` | scalar | `VARCHAR` | immutable |
| `can_cast_implicitly` | scalar | `BOOLEAN` | immutable |
| `create_sort_key` | scalar | unresolved / input-dependent | immutable |
| `current_query` | scalar | `VARCHAR` | stable |
| `nextval` | scalar | `BIGINT` | volatile |
| `setseed` | scalar | unresolved / input-dependent | volatile |
| `txid_current` | scalar | `UBIGINT` | volatile |

<!-- BEGIN GENERATED FUNCTION INVENTORY -->
## Function implementation reference

All function names and implementation symbols are in the single
[function implementation matrix](README.md#function-implementation-matrix).

Source scope: DuckDB 2.0 function reference.
See the [official-source snapshot](function_sources.json) for all source URLs (collected 2026-11-05).
<!-- END GENERATED FUNCTION INVENTORY -->
