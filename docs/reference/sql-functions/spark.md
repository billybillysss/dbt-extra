# Spark function gaps

These 86 entries fill SQLGlot 30.29.0 recognition/semantic gaps, not native
function coverage. Source: [Spark 3.5.7 built-ins](https://spark.apache.org/docs/3.5.7/sql-ref-functions-builtin.html).
Later Spark features are not implied. See [contracts and enrichment examples](README.md).

`scalar` means one value per input row, not one field inside a struct/array.
`aggregate` means one value per group. `generator` marks output-expansion/session
semantics; no generator output schema is fed into YAML inference.
Unresolved types need input/schema/configuration evidence or a future type rule.
All entries remain error/evaluation rewrite barriers. `stable` depends on query,
session or engine context; `volatile` may vary per evaluation; `unknown` is not
assumed deterministic. No nullability, precision or runtime success is certified.

Implementation and executable argument examples:
[catalog](../../../src/dbt_extra/sql/functions/spark.py),
[tests](../../../tests/sql/functions/test_spark.py).

| Function | Kind | Return type policy | Volatility |
| --- | --- | --- | --- |
| `count_min_sketch` | aggregate | `BINARY` | immutable |
| `every` | aggregate | `BOOLEAN` | immutable |
| `histogram_numeric` | aggregate | unresolved / input-dependent | immutable |
| `hll_sketch_agg` | aggregate | `BINARY` | immutable |
| `hll_union_agg` | aggregate | `BINARY` | immutable |
| `mean` | aggregate | unresolved / input-dependent | immutable |
| `some` | aggregate | `BOOLEAN` | immutable |
| `std` | aggregate | `DOUBLE` | immutable |
| `try_avg` | aggregate | unresolved / input-dependent | immutable |
| `try_sum` | aggregate | unresolved / input-dependent | immutable |
| `array_repeat` | scalar | unresolved / input-dependent | immutable |
| `array_union` | scalar | unresolved / input-dependent | immutable |
| `arrays_overlap` | scalar | `BOOLEAN` | immutable |
| `get` | scalar | unresolved / input-dependent | immutable |
| `map_concat` | scalar | unresolved / input-dependent | immutable |
| `map_entries` | scalar | unresolved / input-dependent | immutable |
| `map_values` | scalar | unresolved / input-dependent | immutable |
| `date_part` | scalar | unresolved / input-dependent | immutable |
| `datepart` | scalar | unresolved / input-dependent | immutable |
| `make_date` | scalar | `DATE` | immutable |
| `make_dt_interval` | scalar | unresolved / input-dependent | immutable |
| `make_timestamp_ltz` | scalar | `TIMESTAMP_LTZ` | stable |
| `make_timestamp_ntz` | scalar | `TIMESTAMP_NTZ` | immutable |
| `make_ym_interval` | scalar | unresolved / input-dependent | immutable |
| `now` | scalar | `TIMESTAMP_LTZ` | stable |
| `session_window` | generator | unresolved / input-dependent | immutable |
| `timestamp_micros` | scalar | `TIMESTAMP_LTZ` | immutable |
| `timestamp_millis` | scalar | `TIMESTAMP_LTZ` | immutable |
| `timestamp_seconds` | scalar | `TIMESTAMP_LTZ` | immutable |
| `to_timestamp_ltz` | scalar | `TIMESTAMP_LTZ` | stable |
| `to_timestamp_ntz` | scalar | `TIMESTAMP_NTZ` | immutable |
| `try_to_timestamp` | scalar | unresolved / input-dependent | stable |
| `weekday` | scalar | `INT` | immutable |
| `window` | generator | unresolved / input-dependent | immutable |
| `window_time` | scalar | unresolved / input-dependent | immutable |
| `json_array_length` | scalar | `INT` | immutable |
| `json_tuple` | generator | unresolved / input-dependent | immutable |
| `schema_of_json` | scalar | `STRING` | immutable |
| `bin` | scalar | `STRING` | immutable |
| `bround` | scalar | unresolved / input-dependent | immutable |
| `conv` | scalar | `STRING` | immutable |
| `e` | scalar | `DOUBLE` | immutable |
| `expm1` | scalar | `DOUBLE` | immutable |
| `hypot` | scalar | `DOUBLE` | immutable |
| `log1p` | scalar | `DOUBLE` | immutable |
| `pmod` | scalar | unresolved / input-dependent | immutable |
| `positive` | scalar | unresolved / input-dependent | immutable |
| `btrim` | scalar | `STRING` | immutable |
| `find_in_set` | scalar | `INT` | immutable |
| `format_number` | scalar | `STRING` | immutable |
| `luhn_check` | scalar | `BOOLEAN` | immutable |
| `mask` | scalar | `STRING` | immutable |
| `octet_length` | scalar | `INT` | immutable |
| `printf` | scalar | `STRING` | immutable |
| `sentences` | scalar | `ARRAY<ARRAY<STRING>>` | immutable |
| `to_varchar` | scalar | `STRING` | immutable |
| `try_to_binary` | scalar | `BINARY` | immutable |
| `try_to_number` | scalar | unresolved / input-dependent | immutable |
| `shiftrightunsigned` | scalar | unresolved / input-dependent | immutable |
| `bigint` | scalar | `BIGINT` | immutable |
| `binary` | scalar | `BINARY` | immutable |
| `decimal` | scalar | unresolved / input-dependent | immutable |
| `smallint` | scalar | `SMALLINT` | immutable |
| `tinyint` | scalar | `TINYINT` | immutable |
| `isnotnull` | scalar | `BOOLEAN` | immutable |
| `isnull` | scalar | `BOOLEAN` | immutable |
| `regexp` | scalar | `BOOLEAN` | immutable |
| `from_csv` | scalar | unresolved / input-dependent | immutable |
| `schema_of_csv` | scalar | `STRING` | immutable |
| `to_csv` | scalar | `STRING` | immutable |
| `aes_decrypt` | scalar | `BINARY` | immutable |
| `aes_encrypt` | scalar | `BINARY` | volatile |
| `assert_true` | scalar | unresolved / input-dependent | immutable |
| `hll_sketch_estimate` | scalar | `BIGINT` | immutable |
| `hll_union` | scalar | `BINARY` | immutable |
| `input_file_block_length` | scalar | `BIGINT` | volatile |
| `input_file_block_start` | scalar | `BIGINT` | volatile |
| `input_file_name` | scalar | `STRING` | volatile |
| `java_method` | scalar | unresolved / input-dependent | unknown |
| `monotonically_increasing_id` | scalar | `BIGINT` | volatile |
| `reflect` | scalar | unresolved / input-dependent | unknown |
| `spark_partition_id` | scalar | `INT` | volatile |
| `try_aes_decrypt` | scalar | `BINARY` | immutable |
| `user` | scalar | `STRING` | stable |
| `version` | scalar | `STRING` | stable |
| `inline_outer` | generator | unresolved / input-dependent | immutable |
