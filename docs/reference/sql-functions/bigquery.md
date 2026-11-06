# BigQuery SQL functions

## dbt-extra local function gaps

These unqualified calls remain SQLGlot 30.29.0 `Anonymous` expressions.
Both retain unresolved types and fallible-call rewrite barriers. Recognition does
not evaluate SQL, change AST/spelling or promise warehouse execution compatibility.

The additional [time-series bucket](https://cloud.google.com/bigquery/docs/reference/standard-sql/time-series-functions)
calls have fixed DATE/DATETIME/TIMESTAMP results and two or three arguments.
[Range endpoints](https://cloud.google.com/bigquery/docs/reference/standard-sql/range-functions)
stay input-dependent. Qualified HLL/KLL/ML namespaces are not registered as
unqualified functions; geography and externally supplied table schemas remain separate work.

| Function | Kind | Return policy | Volatility |
| --- | --- | --- | --- |
| `error` | scalar | unresolved / input-dependent | volatile |
| `date_bucket` | scalar | `DATE` | immutable |
| `datetime_bucket` | scalar | `DATETIME` | immutable |
| `timestamp_bucket` | scalar | `TIMESTAMP` | immutable |
| `range_start` | scalar | unresolved / input-dependent | immutable |
| `range_end` | scalar | unresolved / input-dependent | immutable |
| `generate_range_array` | scalar | unresolved / input-dependent | immutable |

- [ERROR](https://cloud.google.com/bigquery/docs/reference/standard-sql/debugging_functions#error)
  takes one error-message argument and always raises if evaluated. GoogleSQL infers
  its type from context; the local entry does not guess a string result or establish
  an evaluation order.
- [GENERATE_RANGE_ARRAY](https://cloud.google.com/bigquery/docs/reference/standard-sql/range-functions#generate_range_array)
  takes a range and interval, optionally a third Boolean controlling the final
  partial range. Its result is `ARRAY<RANGE<T>>`, dependent on the input range.
  It is a **scalar array value**, not a row generator; no nested type is guessed.

Native JSON/range functions and qualified calls such as `HLL_COUNT.INIT` are not
replaced. Table functions such as `RANGE_SESSIONIZE` and `EXTERNAL_QUERY` are
outside this catalog. All tests are offline. See the [audit](audit.md),
[catalog](../../../src/dbt_extra/sql/functions/bigquery.py) and
[per-function regressions](../../../tests/sql/functions/test_bigquery.py).

<!-- BEGIN GENERATED FUNCTION INVENTORY -->
## Function implementation reference

All function names and implementation symbols are in the single
[function implementation matrix](README.md#function-implementation-matrix).

Source scope: GoogleSQL all-functions index (dated snapshot).
See the [official-source snapshot](function_sources.json) for all source URLs (collected 2026-11-05).
<!-- END GENERATED FUNCTION INVENTORY -->
