# Trino SQL functions

## dbt-extra local function gaps

These calls fill SQLGlot 30.29.0 `Anonymous` gaps. All remain fallible-call
rewrite barriers despite immutable classifications. Recognition retains authored
AST/spelling and does not validate argument values or execute functions.

The expanded [array/lambda](https://trino.io/docs/current/functions/array.html),
[map](https://trino.io/docs/current/functions/map.html),
[JSON](https://trino.io/docs/current/functions/json.html) and
[aggregate](https://trino.io/docs/current/functions/aggregate.html) surface follows
current Trino documentation. Lambda/map/histogram outputs remain dependent;
`all_match`/`any_match`/`none_match` return BOOLEAN without granting argument safety.
`CHECKSUM` is an aggregate returning VARBINARY. Native approximate-percentile and
array-position types are corrected separately; native shuffle remains volatile.
Presto-only names such as `array_frequency` are not inferred from ecosystem similarity.

| Function | Kind | Return policy | Volatility |
| --- | --- | --- | --- |
| `bar` | scalar | `VARCHAR` | immutable |
| `human_readable_seconds` | scalar | `VARCHAR` | immutable |
| `contains_sequence` | scalar | `BOOLEAN` | immutable |
| `murmur3` | scalar | `VARBINARY` | immutable |
| `array_histogram` | scalar | unresolved / input-dependent | immutable |
| `all_match` | scalar | `BOOLEAN` | immutable |
| `any_match` | scalar | `BOOLEAN` | immutable |
| `none_match` | scalar | `BOOLEAN` | immutable |
| `map_filter` | scalar | unresolved / input-dependent | immutable |
| `map_zip_with` | scalar | unresolved / input-dependent | immutable |
| `zip_with` | scalar | unresolved / input-dependent | immutable |
| `json_size` | scalar | `BIGINT` | immutable |
| `json_array_length` | scalar | `BIGINT` | immutable |
| `is_json_scalar` | scalar | `BOOLEAN` | immutable |
| `luhn_check` | scalar | `BOOLEAN` | immutable |
| `format_number` | scalar | `VARCHAR` | immutable |
| `to_iso8601` | scalar | `VARCHAR` | immutable |
| `parse_duration` | scalar | unresolved / input-dependent | immutable |
| `checksum` | aggregate | `VARBINARY` | immutable |
| `numeric_histogram` | aggregate | unresolved / input-dependent | immutable |
| `approx_most_frequent` | aggregate | unresolved / input-dependent | immutable |

Signatures and official sources:

- [bar](https://trino.io/docs/current/functions/color.html#bar):
  `bar(x, width)` or `bar(x, width, low_color, high_color)`.
  Exact supported arities are **two or four**, never three.
- [human_readable_seconds](https://trino.io/docs/current/functions/datetime.html#human_readable_seconds):
  one numeric argument; VARCHAR duration text.
- [contains_sequence](https://trino.io/docs/current/functions/array.html#contains_sequence):
  two array arguments; BOOLEAN, with no inferred input-array schema.
- [murmur3](https://trino.io/docs/current/functions/binary.html#murmur3):
  one binary argument; VARBINARY hash, not VARCHAR.

Native `CURRENT_TIMEZONE` remains on the shared SQLGlot path even when its type
is unresolved. Athena does not inherit this catalog. All tests are offline, not
Trino execution certification. See the [audit](audit.md),
[catalog](../../../src/dbt_extra/sql/functions/trino.py) and
[per-function regressions](../../../tests/sql/functions/test_trino.py).

<!-- BEGIN GENERATED FUNCTION INVENTORY -->
## Function implementation reference

All function names and implementation symbols are in the single
[function implementation matrix](README.md#function-implementation-matrix).

Source scope: Trino current function index (dated snapshot).
See the [official-source snapshot](function_sources.json) for all source URLs (collected 2026-11-05).
<!-- END GENERATED FUNCTION INVENTORY -->
