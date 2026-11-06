# Databricks SQL functions

## dbt-extra local function gaps

These entries fill SQLGlot 30.29.0 Anonymous-function gaps, with explicit
Databricks registrations rather than Spark inheritance. Sources: Databricks
[isnull](https://docs.databricks.com/aws/en/sql/language-manual/functions/isnull),
[isnotnull](https://docs.databricks.com/aws/en/sql/language-manual/functions/isnotnull),
[json_array_length](https://docs.databricks.com/aws/en/sql/language-manual/functions/json_array_length),
[schema_of_json](https://docs.databricks.com/aws/en/sql/language-manual/functions/schema_of_json),
[json_tuple](https://docs.databricks.com/aws/en/sql/language-manual/functions/json_tuple),
[inline_outer](https://docs.databricks.com/aws/en/sql/language-manual/functions/inline_outer).

`isnull` and `isnotnull` accept one argument of any type and return BOOLEAN.
`json_array_length` accepts one JSON string and returns INT; malformed JSON/NULL
produces NULL. Known return types do not authorize erasing argument errors.
`schema_of_json` accepts JSON plus an optional
options map. Its result is a STRING describing a schema, not that schema's type.
`json_tuple` requires JSON and at least one key: it produces one row with one STRING
column per key. It remains a generator boundary, with no scalar YAML type or
guessed output schema. SELECT-list invocation is deprecated from Runtime 12.2 LTS;
prefer table-reference invocation on current runtimes. Both shapes are tested.
`inline_outer` accepts one ARRAY of STRUCTs and emits the struct fields as columns,
including one NULL row for NULL/empty input. Literal uniform struct arrays provide
known width; other inputs retain unknown width. It never supplies a scalar YAML
type. Its SELECT-list and table-reference forms both remain generator barriers.

Native `try_add`, `count_if`, and `current_catalog` are not catalog entries;
recognition does not repair native input-dependent inference. All local calls
retain movement/duplication barriers, even with known immutable result types.
Only unused `isnull`/`isnotnull` outputs with independently safe arguments can be
removed; this does not permit moving calls or discarding fallible arguments.

See [contracts and enrichment examples](README.md), the
[catalog](../../../src/dbt_extra/sql/functions/databricks.py), and
[tests](../../../tests/sql/functions/test_databricks.py). Verification is offline,
not Databricks warehouse execution certification.

The expanded catalog independently checks Databricks' aggregate/HLL, collection,
numeric, string, CSV, timestamp and conversion function pages. It also covers
[variant](https://docs.databricks.com/aws/en/sql/language-manual/functions/variant_get),
[variant generators](https://docs.databricks.com/aws/en/sql/language-manual/functions/variant_explode),
[XML](https://docs.databricks.com/aws/en/sql/language-manual/functions/from_xml) and
[bitmap aggregation](https://docs.databricks.com/aws/en/sql/language-manual/functions/bitmap_and_agg).
These are dated documentation contracts, not automatic runtime-version selection:
variant support starts at 15.3 where documented; named generator parameters, newer
optional arguments and beta TIME constructors are not generally claimed.
`variant_get`/`try_variant_get` require three arguments and remain type-dependent;
variant generators have columns `pos`, `key`, `value`, never a scalar metadata type.
`sentences` accepts one or three arguments, not two. `map_concat` also accepts zero
arguments. AES encryption, generated IDs and reflection keep explicit effect barriers.
Deprecated file-input calls and ambiguously documented `arrays_overlap` stay unregistered.

| Function | Kind | Return type policy | Volatility |
| --- | --- | --- | --- |
| `isnull` | scalar | `BOOLEAN` | immutable |
| `isnotnull` | scalar | `BOOLEAN` | immutable |
| `json_array_length` | scalar | `INT` | immutable |
| `schema_of_json` | scalar | `STRING` | immutable |
| `json_tuple` | generator | unresolved / input-dependent | immutable |
| `inline_outer` | generator | unresolved / input-dependent | immutable |
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
| `get` | scalar | unresolved / input-dependent | immutable |
| `map_concat` | scalar | unresolved / input-dependent | immutable |
| `map_entries` | scalar | unresolved / input-dependent | immutable |
| `map_values` | scalar | unresolved / input-dependent | immutable |
| `date_part` | scalar | unresolved / input-dependent | immutable |
| `make_date` | scalar | `DATE` | immutable |
| `make_dt_interval` | scalar | unresolved / input-dependent | immutable |
| `make_timestamp_ltz` | scalar | `TIMESTAMP_LTZ` | stable |
| `make_timestamp_ntz` | scalar | `TIMESTAMP_NTZ` | immutable |
| `make_ym_interval` | scalar | unresolved / input-dependent | immutable |
| `session_window` | generator | unresolved / input-dependent | immutable |
| `timestamp_micros` | scalar | `TIMESTAMP` | immutable |
| `timestamp_millis` | scalar | `TIMESTAMP` | immutable |
| `timestamp_seconds` | scalar | `TIMESTAMP` | immutable |
| `to_timestamp_ltz` | scalar | `TIMESTAMP_LTZ` | stable |
| `to_timestamp_ntz` | scalar | `TIMESTAMP_NTZ` | immutable |
| `try_to_timestamp` | scalar | `TIMESTAMP` | stable |
| `weekday` | scalar | `INT` | immutable |
| `window` | generator | unresolved / input-dependent | immutable |
| `window_time` | scalar | unresolved / input-dependent | immutable |
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
| `decimal` | scalar | `DECIMAL(10,0)` | immutable |
| `smallint` | scalar | `SMALLINT` | immutable |
| `tinyint` | scalar | `TINYINT` | immutable |
| `from_csv` | scalar | unresolved / input-dependent | immutable |
| `schema_of_csv` | scalar | `STRING` | immutable |
| `to_csv` | scalar | `STRING` | immutable |
| `aes_decrypt` | scalar | `BINARY` | immutable |
| `aes_encrypt` | scalar | `BINARY` | volatile |
| `assert_true` | scalar | unresolved / input-dependent | immutable |
| `hll_sketch_estimate` | scalar | `BIGINT` | immutable |
| `hll_union` | scalar | `BINARY` | immutable |
| `java_method` | scalar | `STRING` | unknown |
| `monotonically_increasing_id` | scalar | `BIGINT` | volatile |
| `reflect` | scalar | `STRING` | unknown |
| `try_aes_decrypt` | scalar | `BINARY` | immutable |
| `user` | scalar | `STRING` | stable |
| `version` | scalar | `STRING` | stable |
| `bitmap_and_agg` | aggregate | `BINARY` | immutable |
| `try_parse_json` | scalar | `VARIANT` | immutable |
| `variant_get` | scalar | unresolved / input-dependent | immutable |
| `try_variant_get` | scalar | unresolved / input-dependent | immutable |
| `variant_explode` | generator | unresolved / input-dependent | immutable |
| `variant_explode_outer` | generator | unresolved / input-dependent | immutable |
| `schema_of_variant` | scalar | `STRING` | immutable |
| `schema_of_variant_agg` | aggregate | `STRING` | immutable |
| `schema_of_json_agg` | aggregate | `STRING` | immutable |
| `to_variant_object` | scalar | `VARIANT` | immutable |
| `is_variant_null` | scalar | `BOOLEAN` | immutable |
| `from_xml` | scalar | unresolved / input-dependent | immutable |
| `schema_of_xml` | scalar | `STRING` | immutable |
| `to_xml` | scalar | `STRING` | immutable |

<!-- BEGIN GENERATED FUNCTION INVENTORY -->
## Function implementation reference

All function names and implementation symbols are in the single
[function implementation matrix](README.md#function-implementation-matrix).

Source scope: Databricks built-in alphabetical index (dated snapshot).
See the [official-source snapshot](function_sources.json) for all source URLs (collected 2026-11-05).
<!-- END GENERATED FUNCTION INVENTORY -->
