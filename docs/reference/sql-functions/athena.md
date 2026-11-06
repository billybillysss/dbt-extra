# Athena engine 3 SQL functions

## dbt-extra local function gaps

These calls fill SQLGlot 30.29.0 `Anonymous` gaps using explicit Athena
engine-3 evidence, not automatic Trino inheritance. They preserve authored
AST/spelling and retain `may_raise=True` rewrite barriers.

Additional lambda predicates, JSON inspection, ISO formatting, duration parsing
and checksum aggregation are selected independently within the
[AWS-linked engine-3 function surface](https://docs.aws.amazon.com/athena/latest/ug/functions-env3.html).
This does not import current Trino additions wholesale. Fixed predicate/string
families are inferred; interval and lambda-derived output schemas stay unresolved.
Native array position returns BIGINT and shuffle is a random-permutation barrier.

| Function | Kind | Return policy | Volatility |
| --- | --- | --- | --- |
| `format_number` | scalar | `VARCHAR` | immutable |
| `contains_sequence` | scalar | `BOOLEAN` | immutable |
| `murmur3` | scalar | `VARBINARY` | immutable |
| `invoker_principal` | scalar | `VARCHAR` | stable |
| `all_match` | scalar | `BOOLEAN` | immutable |
| `any_match` | scalar | `BOOLEAN` | immutable |
| `none_match` | scalar | `BOOLEAN` | immutable |
| `json_size` | scalar | `BIGINT` | immutable |
| `json_array_length` | scalar | `BIGINT` | immutable |
| `is_json_scalar` | scalar | `BOOLEAN` | immutable |
| `to_iso8601` | scalar | `VARCHAR` | immutable |
| `parse_duration` | scalar | unresolved / input-dependent | immutable |
| `checksum` | aggregate | `VARBINARY` | immutable |

The [engine-3 reference](https://docs.aws.amazon.com/athena/latest/ug/engine-versions-reference-0003.html)
explicitly documents `format_number(number)` (one argument, abbreviated number
text), `contains_sequence(array, sequence)` (two arguments, BOOLEAN), and
`murmur3(binary)` (one argument, VARBINARY).

[INVOKER_PRINCIPAL](https://docs.aws.amazon.com/athena/latest/ug/functions-env3.html)
takes no arguments and returns the caller's principal ARN as VARCHAR. It depends
on AWS identity context and requires `LakeFormation:GetDataLakePrincipal`.
Recognition neither reads that identity nor grants permissions.

Engine 2, every Trino function and warehouse execution are not certified by these
offline tests. Native `TYPEOF` stays on the shared SQLGlot path. See the
[audit](audit.md), [catalog](../../../src/dbt_extra/sql/functions/athena.py) and
[per-function regressions](../../../tests/sql/functions/test_athena.py).

<!-- BEGIN GENERATED FUNCTION INVENTORY -->
## Function implementation reference

All function names and implementation symbols are in the single
[function implementation matrix](README.md#function-implementation-matrix).

Source scope: Athena engine 3; AWS-linked Trino categories (dated reference, verify availability).
See the [official-source snapshot](function_sources.json) for all source URLs (collected 2026-11-05).
AWS-linked Trino references are candidates, not proof of Athena engine-3
availability; Athena does not inherit Trino's local implementations.
<!-- END GENERATED FUNCTION INVENTORY -->
