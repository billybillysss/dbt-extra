# Remaining-dialect function audit

Reviewed against **SQLGlot 30.29.0** on 2026-11-05. This is a bounded first-pass
inventory across the nine remaining dialects, not an exhaustive warehouse function
list or a complete implementation claim. All nine dialects now have
[explicit local catalogs](README.md); deferred candidates remain below.
Examples were selected for
native behavior, dialect-specific scalar gaps, contextual/side-effecting calls,
input-dependent results, aggregates and generators—not a function-count target.

Reproduce observations from the repository root:

```sh
uv run python scripts/audit_sql_functions.py
uv run python scripts/audit_sql_functions.py --check
```

The script uses this table directly; regression tests check each observation
offline. Official sources establish signatures/type policies, **not** SQLGlot
behavior or optimizer permission. Queries use shared column qualification and
SQLGlot-native type annotation, deliberately excluding local catalogs so that
the dependency baseline remains independent of implemented coverage.
No warehouse calls, environment reads, session
changes or function evaluations are performed. `t.id` is declared `BIGINT`.
Arity counts positional arguments; optional/named argument restrictions still
require review before implementation. Type policy is the documented return family,
not a promise to infer precision, scale, length, nested schemas or coercions.
Volatility is a conservative audit policy, not a catalog of vendor optimizer flags;
local registrations retain movement barriers with `may_raise` defaulting to true.
The dependency-only observations below remain independent of local safety/type fixes.

Of the **68 examples**, 25 use native support, 35 expose recognition gaps, seven
expose native inference gaps and one is a qualified call. These are observations
within this inventory, not total function counts for the dialects. In particular,
the initial Snowflake and BigQuery sample was native; a wider review added six
genuine Anonymous gaps without replacing native nodes.

Classifications:

- `recognition_gap`: the unqualified example is still `exp.Anonymous`; eligible
  for a dialect-local entry after its full signature/safety tests exist.
- `native`: a native AST with an observed type, or a native generator AST. This
  does not certify correctness of the type, generator schema or execution.
- `native_inference_gap`: a native scalar/aggregate AST but no inferred type.
  Do not add these to an Anonymous-only catalog; repair shared inference separately.
- `qualified_call`: a namespaced AST outside the unqualified local lookup.
- `unsupported_syntax`: parsing fails; a catalog entry cannot repair grammar.

The observed type is SQLGlot's output, not an assertion of warehouse equivalence.
Dependency upgrades intentionally require review when these observations change.
Named/qualified forms and unsupported syntax must not be reclassified as local
recognition gaps simply to increase coverage. There are no parser-failure examples
in this first pass; that category remains available for subsequent investigations.

## Inventory

| Dialect | Expression | Arity | Kind | Documented type policy | Volatility | SQLGlot AST | Observed type | Classification | Official source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `duckdb` | `abs(id)` | 1 | scalar | input-dependent numeric | immutable | Abs | BIGINT | native | https://duckdb.org/docs/2.0/sql/functions/numeric.html |
| `duckdb` | `current_setting('threads')` | 1 | scalar | setting-dependent; unresolved | stable | Anonymous | unresolved | recognition_gap | https://duckdb.org/docs/2.0/sql/functions/utility.html |
| `duckdb` | `pg_typeof(id)` | 1 | scalar | VARCHAR | immutable | Anonymous | unresolved | recognition_gap | https://duckdb.org/docs/2.0/sql/functions/utility.html |
| `duckdb` | `stats(id)` | 1 | scalar | VARIANT in DuckDB 2.0; unresolved across versions | stable | Anonymous | unresolved | recognition_gap | https://duckdb.org/docs/2.0/sql/functions/utility.html |
| `duckdb` | `getenv('HOME')` | 1 | scalar | VARCHAR; CLI only | stable | Anonymous | unresolved | recognition_gap | https://duckdb.org/docs/2.0/sql/functions/utility.html |
| `duckdb` | `error('stop')` | 1 | scalar | unresolved; always raises | volatile | Anonymous | unresolved | recognition_gap | https://duckdb.org/docs/2.0/sql/functions/utility.html |
| `duckdb` | `list_transform([1,2], lambda x: x + 1)` | 2 | scalar | lambda/input-dependent LIST | immutable | Transform | unresolved | native_inference_gap | https://duckdb.org/docs/2.0/sql/functions/list.html |
| `postgres` | `abs(id)` | 1 | scalar | input-dependent numeric | immutable | Abs | BIGINT | native | https://www.postgresql.org/docs/18/functions-math.html |
| `postgres` | `pg_typeof(id)` | 1 | scalar | regtype; unresolved | immutable | Anonymous | unresolved | recognition_gap | https://www.postgresql.org/docs/18/functions-info.html |
| `postgres` | `current_setting('search_path')` | 1..2 | scalar | TEXT | stable | Anonymous | unresolved | recognition_gap | https://www.postgresql.org/docs/18/functions-admin.html |
| `postgres` | `set_config('search_path', 'public', false)` | 3 | scalar | TEXT; session mutation | volatile | Anonymous | unresolved | recognition_gap | https://www.postgresql.org/docs/18/functions-admin.html |
| `postgres` | `pg_backend_pid()` | 0 | scalar | INTEGER | stable | Anonymous | unresolved | recognition_gap | https://www.postgresql.org/docs/18/functions-info.html |
| `postgres` | `pg_is_in_recovery()` | 0 | scalar | BOOLEAN | volatile | Anonymous | unresolved | recognition_gap | https://www.postgresql.org/docs/18/functions-admin.html |
| `postgres` | `jsonb_path_exists('{}'::jsonb, '$.a')` | 2..4 | scalar | BOOLEAN | immutable | Anonymous | unresolved | recognition_gap | https://www.postgresql.org/docs/18/functions-json.html |
| `postgres` | `generate_series(1, 3)` | 2..3 numeric; 3..4 timestamp | generator | input-dependent set | stable | ExplodingGenerateSeries | not_scalar | native | https://www.postgresql.org/docs/18/functions-srf.html |
| `snowflake` | `abs(id)` | 1 | scalar | input-dependent numeric | immutable | Abs | BIGINT | native | https://docs.snowflake.com/en/sql-reference/functions/abs |
| `snowflake` | `try_to_double('1.5')` | 1..2 | scalar | FLOAT | immutable | ToDouble | DOUBLE | native | https://docs.snowflake.com/en/sql-reference/functions/try_to_double |
| `snowflake` | `check_json('{}')` | 1 | scalar | VARCHAR | immutable | CheckJson | VARCHAR | native | https://docs.snowflake.com/en/sql-reference/functions/check_json |
| `snowflake` | `is_array(parse_json('[]'))` | 1 | scalar | BOOLEAN | immutable | IsArray | unresolved | native_inference_gap | https://docs.snowflake.com/en/sql-reference/functions/is_array |
| `snowflake` | `typeof(parse_json('1'))` | 1 | scalar | VARCHAR | immutable | Typeof | VARCHAR | native | https://docs.snowflake.com/en/sql-reference/functions/typeof |
| `snowflake` | `current_warehouse()` | 0 | scalar | VARCHAR | stable | CurrentWarehouse | VARCHAR | native | https://docs.snowflake.com/en/sql-reference/functions/current_warehouse |
| `snowflake` | `seq4()` | 0..1 | scalar | INTEGER | volatile | Seq4 | INT | native | https://docs.snowflake.com/en/sql-reference/functions/seq1 |
| `snowflake` | `get_ddl('TABLE', 't')` | 2..3 | scalar | VARCHAR; object/session-dependent | stable | Anonymous | unresolved | recognition_gap | https://docs.snowflake.com/en/sql-reference/functions/get_ddl |
| `snowflake` | `last_query_id()` | 0..1 | scalar | VARCHAR; session query ID | volatile | Anonymous | unresolved | recognition_gap | https://docs.snowflake.com/en/sql-reference/functions/last_query_id |
| `snowflake` | `is_role_in_session('PUBLIC')` | 1 | scalar | BOOLEAN | stable | Anonymous | unresolved | recognition_gap | https://docs.snowflake.com/en/sql-reference/functions/is_role_in_session |
| `snowflake` | `is_database_role_in_session('reader')` | 1 | scalar | BOOLEAN | stable | Anonymous | unresolved | recognition_gap | https://docs.snowflake.com/en/sql-reference/functions/is_database_role_in_session |
| `bigquery` | `abs(id)` | 1 | scalar | input-dependent numeric | immutable | Abs | INT64 | native | https://cloud.google.com/bigquery/docs/reference/standard-sql/mathematical_functions#abs |
| `bigquery` | `generate_uuid()` | 0 | scalar | STRING | volatile | Uuid | STRING | native | https://cloud.google.com/bigquery/docs/reference/standard-sql/utility-functions#generate_uuid |
| `bigquery` | `typeof(id)` | 1 | scalar | STRING | immutable | Typeof | STRING | native | https://cloud.google.com/bigquery/docs/reference/standard-sql/utility-functions#typeof |
| `bigquery` | `json_strip_nulls(JSON '{}')` | 1..4; last two named-only | scalar | JSON | immutable | JSONStripNulls | JSON | native | https://cloud.google.com/bigquery/docs/reference/standard-sql/json_functions#json_strip_nulls |
| `bigquery` | `json_keys(JSON '{}')` | 1..3; mode named-only | scalar | ARRAY of STRING | immutable | JSONKeysAtDepth | ARRAY<STRING> | native | https://cloud.google.com/bigquery/docs/reference/standard-sql/json_functions#json_keys |
| `bigquery` | `range_bucket(5, [0, 10, 20])` | 2 | scalar | INT64 | immutable | RangeBucket | INT64 | native | https://cloud.google.com/bigquery/docs/reference/standard-sql/mathematical_functions#range_bucket |
| `bigquery` | `HLL_COUNT.INIT(id)` | 1..2 | aggregate | BYTES | immutable | Dot | unresolved | qualified_call | https://cloud.google.com/bigquery/docs/reference/standard-sql/hll_functions#hll_countinit |
| `bigquery` | `normalize_and_casefold('ABC')` | 1..2 | scalar | STRING | immutable | Normalize | STRING | native | https://cloud.google.com/bigquery/docs/reference/standard-sql/string_functions#normalize_and_casefold |
| `bigquery` | `error('stop')` | 1 | scalar | contextual; unresolved; always raises | volatile | Anonymous | unresolved | recognition_gap | https://cloud.google.com/bigquery/docs/reference/standard-sql/debugging_functions#error |
| `bigquery` | `generate_range_array(RANGE(DATE '2020-01-01', DATE '2020-02-01'), INTERVAL 1 DAY)` | 2..3 | scalar | ARRAY of RANGE of input-dependent type; unresolved | immutable | Anonymous | unresolved | recognition_gap | https://cloud.google.com/bigquery/docs/reference/standard-sql/range-functions#generate_range_array |
| `fabric` | `abs(id)` | 1 | scalar | input-dependent numeric | immutable | Abs | BIGINT | native | https://learn.microsoft.com/en-us/sql/t-sql/functions/abs-transact-sql?view=fabric |
| `fabric` | `isjson('{}')` | 1..2 | scalar | INT | immutable | Anonymous | unresolved | recognition_gap | https://learn.microsoft.com/en-us/sql/t-sql/functions/isjson-transact-sql?view=fabric |
| `fabric` | `json_path_exists('{}', '$.a')` | 2 | scalar | INT | immutable | Anonymous | unresolved | recognition_gap | https://learn.microsoft.com/en-us/sql/t-sql/functions/json-path-exists-transact-sql?view=fabric |
| `fabric` | `string_split('a,b', ',')` | 2; third argument needs Warehouse-specific evidence | generator | input-dependent string | immutable | Anonymous | not_scalar | recognition_gap | https://learn.microsoft.com/en-us/sql/t-sql/functions/string-split-transact-sql?view=fabric |
| `fabric` | `json_value('{}', '$.a')` | 2; RETURNING/version restrictions | scalar | NVARCHAR(4000) absent RETURNING | immutable | JSONExtractScalar | unresolved | native_inference_gap | https://learn.microsoft.com/en-us/sql/t-sql/functions/json-value-transact-sql?view=fabric |
| `databricks` | `abs(id)` | 1 | scalar | input-dependent numeric | immutable | Abs | BIGINT | native | https://docs.databricks.com/aws/en/sql/language-manual/functions/abs |
| `databricks` | `isnull(id)` | 1 | scalar | BOOLEAN | immutable | Anonymous | unresolved | recognition_gap | https://docs.databricks.com/aws/en/sql/language-manual/functions/isnull |
| `databricks` | `try_add(1, 2)` | 2 | scalar | input-dependent numeric/date/interval | immutable | SafeAdd | unresolved | native_inference_gap | https://docs.databricks.com/aws/en/sql/language-manual/functions/try_add |
| `databricks` | `schema_of_json('{}')` | 1..2 | scalar | STRING | immutable | Anonymous | unresolved | recognition_gap | https://docs.databricks.com/aws/en/sql/language-manual/functions/schema_of_json |
| `databricks` | `json_tuple('{}', 'a')` | 2+ | generator | one STRING column per key | immutable | Anonymous | not_scalar | recognition_gap | https://docs.databricks.com/aws/en/sql/language-manual/functions/json_tuple |
| `databricks` | `count_if(id > 0)` | 1 | aggregate | BIGINT | immutable | CountIf | BIGINT | native | https://docs.databricks.com/aws/en/sql/language-manual/functions/count_if |
| `databricks` | `current_catalog()` | 0 | scalar | STRING | stable | CurrentCatalog | STRING | native | https://docs.databricks.com/aws/en/sql/language-manual/functions/current_catalog |
| `redshift` | `abs(id)` | 1 | scalar | input-dependent numeric | immutable | Abs | BIGINT | native | https://docs.aws.amazon.com/redshift/latest/dg/r_ABS.html |
| `redshift` | `fnv_hash('abc')` | 1..2 | scalar | BIGINT | immutable | Anonymous | unresolved | recognition_gap | https://docs.aws.amazon.com/redshift/latest/dg/r_FNV_HASH.html |
| `redshift` | `can_json_parse('{}')` | 1 | scalar | BOOLEAN | immutable | Anonymous | unresolved | recognition_gap | https://docs.aws.amazon.com/redshift/latest/dg/CAN_JSON_PARSE.html |
| `redshift` | `json_typeof(json_parse('{}'))` | 1 | scalar | VARCHAR | immutable | Anonymous | unresolved | recognition_gap | https://docs.aws.amazon.com/redshift/latest/dg/r_json_typeof.html |
| `redshift` | `pg_last_query_id()` | 0 | scalar | INTEGER | volatile | Anonymous | unresolved | recognition_gap | https://docs.aws.amazon.com/redshift/latest/dg/PG_LAST_QUERY_ID.html |
| `redshift` | `soundex('hello')` | 1 | scalar | VARCHAR(4) | immutable | Soundex | unresolved | native_inference_gap | https://docs.aws.amazon.com/redshift/latest/dg/SOUNDEX.html |
| `redshift` | `json_extract_path_text('{}', 'a')` | 2..7; up to five path elements and null_if_invalid | scalar | VARCHAR | immutable | JSONExtractScalar | unresolved | native_inference_gap | https://docs.aws.amazon.com/redshift/latest/dg/JSON_EXTRACT_PATH_TEXT.html |
| `trino` | `abs(id)` | 1 | scalar | input-dependent numeric | immutable | Abs | BIGINT | native | https://trino.io/docs/current/functions/math.html#abs |
| `trino` | `bar(0.5, 10)` | 2 or 4 | scalar | VARCHAR | immutable | Anonymous | unresolved | recognition_gap | https://trino.io/docs/current/functions/color.html#bar |
| `trino` | `typeof(id)` | 1 | scalar | VARCHAR | immutable | Typeof | VARCHAR | native | https://trino.io/docs/current/functions/conversion.html#typeof |
| `trino` | `current_timezone()` | 0 | scalar | VARCHAR | stable | CurrentTimezone | unresolved | native_inference_gap | https://trino.io/docs/current/functions/datetime.html#current_timezone |
| `trino` | `human_readable_seconds(3600)` | 1 | scalar | VARCHAR | immutable | Anonymous | unresolved | recognition_gap | https://trino.io/docs/current/functions/datetime.html#human_readable_seconds |
| `trino` | `contains_sequence(ARRAY[1,2,3], ARRAY[1,2])` | 2 | scalar | BOOLEAN | immutable | Anonymous | unresolved | recognition_gap | https://trino.io/docs/current/functions/array.html#contains_sequence |
| `trino` | `murmur3(to_utf8('abc'))` | 1 | scalar | VARBINARY | immutable | Anonymous | unresolved | recognition_gap | https://trino.io/docs/current/functions/binary.html#murmur3 |
| `athena` | `abs(id)` | 1 | scalar | input-dependent numeric | immutable | Abs | BIGINT | native | https://docs.aws.amazon.com/athena/latest/ug/functions-env3.html |
| `athena` | `format_number(123456)` | 1 | scalar | VARCHAR | immutable | Anonymous | unresolved | recognition_gap | https://docs.aws.amazon.com/athena/latest/ug/engine-versions-reference-0003.html |
| `athena` | `contains_sequence(ARRAY[1,2,3], ARRAY[1,2])` | 2 | scalar | BOOLEAN | immutable | Anonymous | unresolved | recognition_gap | https://docs.aws.amazon.com/athena/latest/ug/engine-versions-reference-0003.html |
| `athena` | `murmur3(to_utf8('abc'))` | 1 | scalar | VARBINARY | immutable | Anonymous | unresolved | recognition_gap | https://docs.aws.amazon.com/athena/latest/ug/engine-versions-reference-0003.html |
| `athena` | `typeof(id)` | 1 | scalar | VARCHAR | immutable | Typeof | VARCHAR | native | https://docs.aws.amazon.com/athena/latest/ug/functions-env3.html |
| `athena` | `invoker_principal()` | 0 | scalar | VARCHAR; requires Lake Formation permissions | stable | Anonymous | unresolved | recognition_gap | https://docs.aws.amazon.com/athena/latest/ug/functions-env3.html |

## Implementation decisions

- Fabric (three entries), Databricks (six), DuckDB (four) and PostgreSQL (six)
  now have explicit registrations with per-function tests. Fabric and Databricks
  do not inherit the existing Spark/T-SQL catalogs. Snowflake (four), BigQuery (two),
  Redshift (four), Trino (four) and Athena (four) complete the remaining batches.
  This inventory is not itself runtime registration; DuckDB `getenv` remains deferred.
- An input-dependent or vendor-specific type remains unresolved until its policy
  is proven. In particular PostgreSQL `regtype` is not automatically TEXT,
  DuckDB settings are not universally strings, and Databricks `try_add` is not
  universally numeric. CLI-only DuckDB `getenv` is not a general warehouse builtin.
- PostgreSQL `set_config`, Snowflake `seq4` and context-sensitive calls need
  rewrite barriers irrespective of whether a fixed return type is known.
- BigQuery named-only arguments, Trino's disjoint overload arities, Fabric
  version-specific overloads and Databricks generator columns need more than a simple
  permissive minimum/maximum range. Registered Databricks `json_tuple` has an
  explicit per-key shape rule; Fabric `string_split` registers only two arguments.
  Trino `bar` now uses exact arities `(2, 4)` and rejects three arguments.
  BigQuery `generate_range_array` returns one scalar array, not generated rows;
  its dependent nested type and contextual `error` result remain unresolved.
  Do not implement unsupported overloads.
- The XACT_STATE and DATALENGTH pages list SQL database in Fabric, not Warehouse
  or its SQL analytics endpoint. They are deferred, not assumed available through
  T-SQL inheritance. STRING_SPLIT's optional ordinal argument likewise needs
  Warehouse-specific evidence before registration.
- Athena evidence is engine-version-3-specific. Its AWS reference links to Trino,
  but this is not permission to inherit Trino's local catalog or every new function.
- Native inference gaps and qualified calls need separate upstream/shared-path
  handling; the Anonymous registry must not replace native ASTs. The shared path
  now annotates Snowflake `is_array`, Redshift `soundex`/`json_extract_path_text`
  and Trino `current_timezone` with their fixed return families. The table still
  records unmodified SQLGlot observations. Dependent/version-sensitive gaps and
  the qualified BigQuery call remain unresolved.
