# Snowflake SQL functions

## dbt-extra local function gaps

These unqualified calls remain SQLGlot 30.29.0 `Anonymous` expressions.
Recognition preserves their AST/spelling; fixed type families grant no permission
to move, duplicate, remove or evaluate them. All retain `may_raise=True` barriers.

Additional predicates use Snowflake's own
[semi-structured function contracts](https://docs.snowflake.com/en/sql-reference/functions-semistructured).
`OBJECT_PICK`/`OBJECT_DELETE` remain dependent on structured versus semi-structured
input. [HASH](https://docs.snowflake.com/en/sql-reference/functions/hash) returns
NUMBER(19,0), not a guessed generic integer. `HLL_ESTIMATE` is an aggregate boundary
with no guessed return precision. `RESULT_SCAN` is a context-sensitive table source
with unknown output schema. Native `TO_NUMBER` separately honors literal precision/scale.

| Function | Kind | Return policy | Volatility |
| --- | --- | --- | --- |
| `get_ddl` | scalar | `VARCHAR` | stable |
| `last_query_id` | scalar | `VARCHAR` | volatile |
| `is_role_in_session` | scalar | `BOOLEAN` | stable |
| `is_database_role_in_session` | scalar | `BOOLEAN` | stable |
| `is_object` | scalar | `BOOLEAN` | immutable |
| `is_boolean` | scalar | `BOOLEAN` | immutable |
| `is_integer` | scalar | `BOOLEAN` | immutable |
| `is_decimal` | scalar | `BOOLEAN` | immutable |
| `is_double` | scalar | `BOOLEAN` | immutable |
| `is_date_value` | scalar | `BOOLEAN` | immutable |
| `is_timestamp_ntz` | scalar | `BOOLEAN` | immutable |
| `object_pick` | scalar | unresolved / input-dependent | immutable |
| `object_delete` | scalar | unresolved / input-dependent | immutable |
| `hll_estimate` | aggregate | unresolved / input-dependent | immutable |
| `hash` | scalar | `NUMBER(19,0)` | immutable |
| `result_scan` | generator | unresolved / input-dependent | volatile |

Signatures and official sources:

- [GET_DDL](https://docs.snowflake.com/en/sql-reference/functions/get_ddl):
  two or three arguments; returns DDL text, not an execution request. Object
  visibility, privileges and session settings affect the result.
- [LAST_QUERY_ID](https://docs.snowflake.com/en/sql-reference/functions/last_query_id):
  zero or one argument; session query-history ID, not an integer counter.
- [IS_ROLE_IN_SESSION](https://docs.snowflake.com/en/sql-reference/functions/is_role_in_session):
  one argument; nullable Boolean based on active roles and execution context.
- [IS_DATABASE_ROLE_IN_SESSION](https://docs.snowflake.com/en/sql-reference/functions/is_database_role_in_session):
  one argument; database-context-sensitive Boolean. Vendor restrictions on inline
  views, role names and policies still apply; recognition does not validate them.

Native nodes such as `IS_ARRAY`, `CHECK_JSON`, `SEQ4` and `TRY_TO_DOUBLE` are
not replaced, including native inference gaps. These checks are offline, not
Snowflake execution certification. See the [audit](audit.md),
[catalog](../../../src/dbt_extra/sql/functions/snowflake.py) and
[per-function regressions](../../../tests/sql/functions/test_snowflake.py).

<!-- BEGIN GENERATED FUNCTION INVENTORY -->
## Function implementation reference

All function names and implementation symbols are in the single
[function implementation matrix](README.md#function-implementation-matrix).

Source scope: Snowflake all-functions index (dated snapshot).
See the [official-source snapshot](function_sources.json) for all source URLs (collected 2026-11-05).
<!-- END GENERATED FUNCTION INVENTORY -->
