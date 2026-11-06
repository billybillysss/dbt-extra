# SQL functions: implementation ownership and enrichment

SQL-function enrichment infers missing column data types from statically
analyzable expressions using SQLGlot and available schema evidence. Function
coverage varies by dialect and input types. Parsing support does not guarantee
type inference or safe optimization.

## Why dbt-extra defines SQL function semantics

SQLGlot can preserve a call such as `isnotnull(id)` as an Anonymous expression
without knowing its dialect-specific behavior. An unknown call might be a scalar,
aggregate or row generator; it might also raise an error, observe session state or
produce a different result on each evaluation. Optimizing it as an ordinary pure
scalar could change the query's results, errors or row counts.

dbt-extra's function definitions are **local semantic metadata for existing
warehouse functions**, not new warehouse UDFs or Python implementations of SQL.
They describe supported argument counts, result types, output shape and effects.
Lookup is dialect-specific: the same spelling can have different signatures or
behavior, and related dialects do not inherit local catalogs automatically.
Inference does not execute the function; recognition preserves the original AST.

This metadata improves analysis and gives optimization rules evidence to use, but
**recognizing a function does not make every rewrite safe**. A deterministic call
can still raise an error. A known return type does not prove that an evaluation
can be removed, duplicated or moved. Each rewrite needs its own proof, including
the safety of the arguments. Current local catalog entries retain general
movement/duplication barriers; narrowly proven output removal is separate.

### Example: remove a proven-safe unused null check

These examples use the Spark dialect and a complete declared schema of
`t.id BIGINT`. Before optimization:

```sql
SELECT q.id
FROM (
  SELECT id, isnotnull(id) AS unused_check
  FROM t
) q;
```

After optimization:

```sql
SELECT
  a.id
FROM t AS a;
```

The outer query does not use `unused_check`. The null check is total, and its
column argument is independently discardable, so the unused projection can be
removed and the remaining simple subquery merged. This is a specific removal
proof, not blanket permission to move local functions. An unused
`isnotnull(CAST(value AS INT))` would be retained because the cast can raise.

### Example: optimize around an unknown function

A function does not need a local definition for independent safe work to proceed.
Before optimization:

```sql
SELECT q.id, q.result, 1 + 2 AS constant_value
FROM (
  SELECT id, mystery(id) AS result, id AS unused
  FROM t
) q;
```

After optimization:

```sql
SELECT
  q.id,
  q.result,
  3 AS constant_value
FROM (
  SELECT
    a.id,
    MYSTERY(a.id) AS result
  FROM t AS a
) AS q;
```

`MYSTERY` remains opaque and its evaluation stays inside the subquery. The unused
plain-column projection is still removed, and the independent literal expression
is folded. Unknown behavior does not automatically make the entire query a no-op.

The [partial optimization workflow](../../guides/partial-optimization.md) applies
eligible rules and regions independently. A recoverable candidate failure rolls
back that candidate, retaining earlier validated work. Some rules still have
whole-query guards, and final output/binding/round-trip checks still apply;
unparseable SQL and programming errors are not silently ignored. Local semantics
and partial optimization complement each other: one supplies function evidence,
while the other limits how unsupported or rejected work blocks independent steps.

## Reading the matrix

The [function implementation matrix](#function-implementation-matrix) has one row
per SQL function spelling and one column per dialect. It includes functions
implemented by neither library; dialect pages retain detailed local type policies
instead of repeating the inventories.

The alphabetical matrix covers all names in the checked-in
[official-source snapshot](function_sources.json), SQLGlot's `FUNCTIONS`,
`FUNCTION_PARSERS`, and `NO_PAREN_FUNCTIONS` registries, plus each dialect's
dbt-extra catalog. Typed casts/keyword functions outside those registries are
also probed for the documented names. Each cell uses these symbols:

- **S — SQLGlot**: upstream named recognition, including inherited parser registrations.
- **E — dbt-extra**: local recognition/semantics for an otherwise Anonymous call;
  SQLGlot still supplies the underlying parser and AST. The local tables below
  document supported arities, shape and unresolved return types.
- **B — both**: a native function with a reviewed dbt-extra return-type repair,
  including fixed families and argument-dependent overloads. Native AST nodes
  and SQLGlot's global registries are unchanged. This does not certify every overload.
- **× — neither**: a documented name with no named recognition/semantics found in
  either library. Acceptance as an Anonymous/qualified call is not implementation.
  This is not a claim that the warehouse itself lacks the function.
- **— — not listed**: absent from this dialect's reviewed source snapshot,
  named SQLGlot registrations and local catalog. This is not proof of warehouse
  incompatibility, nor a claim that an unlisted function is implemented.

Official indexes add unimplemented functions that a registry-only list would
miss. The snapshot records source versions/URLs and its collection date; rolling
cloud references are dated rather than assigned an invented engine version.
Fabric names require explicit Warehouse/SQL analytics endpoint applies-to
evidence, not merely Fabric SQL Database or T-SQL inheritance. Athena includes
the Trino categories linked by AWS: these are reference candidates, not engine-3
availability certification or inheritance of Trino's local implementations.

The matrix exhausts the **enumerated snapshot and registries**, not every
warehouse builtin, extension, overload or UDF. Source extraction excludes
wildcard/group labels and unnamed/operator-only entries; functions documented
outside the collected indexes may be absent. SQLGlot's permissive inherited
registrations can include names a particular warehouse does not execute. Special
SQL syntax not represented by the named sources is not enumerated. A SQLGlot row
does not certify any overload's return type, rewrite safety or warehouse
availability. Unlisted functions are not necessarily unsupported. The existing
per-function local policies and reviewed [audit](audit.md) remain the evidence for
inferred and unresolved results; ownership does not turn unresolved into inferred.

The matrix is generated from the installed SQLGlot and current local
catalogs and checked-in source snapshot; they do not modify runtime behavior.
Normal generation/checking is offline. The same generator updates catalog counts
and the dialect pages' four-column catalog tables, preserving surrounding
handwritten policies and examples. Regenerate after reviewing a
dependency/catalog change, then check for drift:

```bash
uv run python scripts/generate_sql_function_docs.py --write
uv run python scripts/generate_sql_function_docs.py --check
```

To refresh the official name snapshot separately (requires network access), run
`uv run python scripts/collect_sql_function_sources.py`, review
`function_sources.json`, then regenerate and test. This does not execute SQL or
install warehouse functions.

## Implemented dialect catalogs

| SQLGlot dialect | Local function gaps | Function catalog | Separate regression suite |
| --- | --- | --- | --- |
| `spark` | 86 | [Spark type policies](spark.md) | [Spark tests](../../../tests/sql/functions/test_spark.py) |
| `tsql` | 76 | [T-SQL type policies](tsql.md) | [T-SQL tests](../../../tests/sql/functions/test_tsql.py) |
| `fabric` | 14 | [Fabric Warehouse type policies](fabric.md) | [Fabric tests](../../../tests/sql/functions/test_fabric.py) |
| `databricks` | 92 | [Databricks type policies](databricks.md) | [Databricks tests](../../../tests/sql/functions/test_databricks.py) |
| `duckdb` | 24 | [DuckDB type policies](duckdb.md) | [DuckDB tests](../../../tests/sql/functions/test_duckdb.py) |
| `postgres` | 36 | [PostgreSQL type policies](postgres.md) | [PostgreSQL tests](../../../tests/sql/functions/test_postgres.py) |
| `snowflake` | 16 | [Snowflake type policies](snowflake.md) | [Snowflake tests](../../../tests/sql/functions/test_snowflake.py) |
| `bigquery` | 7 | [BigQuery type policies](bigquery.md) | [BigQuery tests](../../../tests/sql/functions/test_bigquery.py) |
| `redshift` | 20 | [Redshift type policies](redshift.md) | [Redshift tests](../../../tests/sql/functions/test_redshift.py) |
| `trino` | 21 | [Trino type policies](trino.md) | [Trino tests](../../../tests/sql/functions/test_trino.py) |
| `athena` | 13 | [Athena engine 3 type policies](athena.md) | [Athena tests](../../../tests/sql/functions/test_athena.py) |

These **405 dialect-local entries** fill demonstrated SQLGlot 30.29.0 gaps
(some function names occur in more than one dialect):
each example still parses as `exp.Anonymous` without dbt-extra. Native functions
such as `UPPER`, `SUM`, `EXPLODE`, `OPENJSON` and `JSON_VALUE` are not counted.
Each local entry is tested for recognition, shape, type inference, rewrite safety,
and YAML enrichment. Type-policy `unresolved / input-dependent` is intentional:
recognizing a scalar, aggregate or generator does not justify guessing its type.

Recognition preserves the original SQLGlot AST and function spelling, with a
dialect-local semantic lookup. It does not relabel every Anonymous expression as
scalar, modify SQLGlot globally, or authorize SQL-function evaluation. Scalar and
aggregate calls return one value; generators may emit multiple columns or change
row counts. Spark/Databricks `JSON_TUPLE` arity follows its key arguments;
T-SQL `STRING_SPLIT` has one column by default and two with literal ordinal flag
`1`. Fabric registers only the two-argument, one-column form. `INLINE_OUTER` can use
literal struct width; otherwise its column count remains unknown. Spark/Databricks
`WINDOW` and `SESSION_WINDOW` are conservative expansion/session barriers, not movable scalars.
Databricks variant generators have three columns; PostgreSQL JSON set-returning
calls and native `generate_series` are generator boundaries too. DuckDB's
`generate_series` remains a scalar list, not a PostgreSQL-style row generator.

All local calls retain movement/duplication barriers, including deterministic calls
that may raise, environment-sensitive functions, reflection and `try_*` functions.
No folding, removal, duplication or movement permission follows from an inferred
type. One separate removal proof permits pruning unused Spark/Databricks `isnull`
and `isnotnull` outputs only when every argument is independently discardable.
Casts, arithmetic, volatile/unknown calls and comments prevent this removal;
live aliases, ordering/grouping dependencies and positional references remain intact.
The dependency-analysis copy exposes these null checks as scalar predicates;
retained authored function nodes/spelling are not replaced.
Unknown names, schema-qualified/quoted calls, and unsupported argument counts
remain unknown. Generator queries cannot provide metadata types/lineage until
their output schema is established. No window-function gap is currently claimed.

All eleven dialects in the shared SQL regression matrix now have explicit local
gap catalogs. SQLGlot-native inference remains available; the local gap catalogs
are not exhaustive function inventories or warehouse certification. Related
dialects do not inherit local catalogs implicitly. Athena evidence is engine-3-specific.

The [remaining-dialect audit](audit.md) records a reproducible, bounded inventory
of native functions, Anonymous recognition gaps and native type-inference gaps,
with official sources and conservative signature/type/safety policies. It is
evidence for both implemented and deferred candidates, not additional coverage.
CLI-only DuckDB `getenv` and unproven Fabric overloads remain unregistered.

The shared inference path also repairs **native** types without adding Anonymous
catalog entries or replacing AST nodes. These include fixed families and reviewed
numeric overloads; see [native corrections](#native-corrections-and-review-limits).
Uncertified input-dependent cases (`try_add`, lambda/list results) and
version-sensitive Fabric `JSON_VALUE` remain unresolved. Native sequence/random,
secret/AI-service and current/session-context calls retain evaluation barriers,
including `SEQ1/2/4/8`, `SHUFFLE`, `UNIFORM`, `SECRET`, `CURRENT_WAREHOUSE`,
`CURRENT_CATALOG` and `CURRENT_TIMEZONE`, irrespective of inferred types.
Unreviewed native function effects default to unknown, not immutable. The bounded
immutable allowlist is not a totality proof: its members may still raise errors.

Catalog lookup accepts validated dialect strings with settings, such as
`spark, normalization_strategy=case_sensitive`, while preserving the full dialect
for parsing, metadata and type inference. Registrations are checked for duplicates
before dictionary construction. Generator shape rules are explicit per dialect
and function; an unhandled generator has unknown width and cardinality, never an
inferred `INLINE_OUTER` shape.
Disjoint signatures use exact arities: Trino `bar` accepts two or four arguments,
not three. BigQuery `generate_range_array` is a scalar array with an unresolved
input-dependent nested type, not a row generator; `error` has no fixed result type.

## Native corrections and review limits

The broader review checked recognition, types and effects separately across all
eleven dialects. A function can parse natively and still have an incorrect type or
unsafe effect classification. The matrix's **S** therefore means recognition,
not type correctness. **B** identifies reviewed native type corrections:

| Area | Reviewed correction |
| --- | --- |
| Array position | Scalar INTEGER in PostgreSQL/DuckDB; BIGINT in Spark/Databricks/Trino/Athena, not the input array type. |
| Semi-structured values | Redshift `JSON_PARSE` yields SUPER; Databricks `PARSE_JSON` yields VARIANT. |
| Numeric aggregates | Dialect- and input-specific `SUM`/`AVG` integer and decimal widening in PostgreSQL, DuckDB, T-SQL, Fabric, Redshift, Spark and Databricks. PostgreSQL numeric statistical aggregates also retain numeric families. |
| Numeric conversion | Snowflake `TO_NUMBER` honors literal precision/scale instead of always reporting NUMBER(38,0). |
| Approximate percentile | Trino scalar/array overloads preserve the value type; DuckDB's reviewed integer/floating overloads do likewise. |
| DuckDB scalar overloads | Correct position/sign/week integer widths, timezone-aware timestamp/time results, integral/floating `ROUND`, BLOB/list `REPEAT`, and scalar/list JSON string extraction. |
| Fixed native gaps | Snowflake `IS_ARRAY`, Redshift `SOUNDEX`/`JSON_EXTRACT_PATH_TEXT`, Trino `CURRENT_TIMEZONE`. |

For example, with declared `BIGINT` input, `SUM` is HUGEINT in DuckDB, NUMERIC in
PostgreSQL and BIGINT in T-SQL; `AVG(BIGINT)` is NUMERIC in PostgreSQL but BIGINT
in T-SQL/Redshift. For `DECIMAL(12,2)`, `SUM` is DECIMAL(38,2) in DuckDB/T-SQL/
Fabric/Redshift and DECIMAL(22,2) in Spark/Databricks. These annotations propagate
through nested queries and enrich only missing YAML types; authored metadata stays intact.

Evidence comes from official [PostgreSQL aggregates](https://www.postgresql.org/docs/18/functions-aggregate.html),
[Microsoft SUM](https://learn.microsoft.com/en-us/sql/t-sql/functions/sum-transact-sql)
and [AVG](https://learn.microsoft.com/en-us/sql/t-sql/functions/avg-transact-sql),
[Redshift AVG](https://docs.aws.amazon.com/redshift/latest/dg/r_AVG.html),
[Spark 3.5 aggregate source](https://github.com/apache/spark/tree/v3.5.7/sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/aggregate),
[Databricks SUM](https://docs.databricks.com/aws/en/sql/language-manual/functions/sum)
and [AVG](https://docs.databricks.com/aws/en/sql/language-manual/functions/avg),
and [Trino aggregates](https://trino.io/docs/current/functions/aggregate.html).
DuckDB regression tests additionally compare inferred types with the installed
engine's in-memory `DESCRIBE` binder, without evaluating candidate functions.

Important bounds of this expansion:

- Catalogs remain explicit per dialect. Databricks registrations were checked
  against its own function pages, not copied implicitly from Spark. Fabric additions
  require explicit Warehouse applicability. Athena additions stay within its
  separately reviewed engine-3 reference surface, not the entire current Trino catalog.
- Cloud documentation is a dated availability reference, not a runtime-version
  negotiator. Databricks variant functions require 15.3+ where documented; newer
  HLL/XML/bitmap families and optional overloads have their own runtime requirements.
  Beta TIME constructor overloads and deprecated file-input functions are not added.
- Ambiguous Databricks `arrays_overlap` return documentation stays unresolved and
  unregistered. Its documented SUM decimal cap is not extrapolated for precision
  above 21; those cases remain unresolved. DuckDB decimal `ROUND` and approximate
  percentile cases also stay unresolved rather than retaining known-wrong guesses.
- Lambda/map element types, format/schema-derived results, BigQuery qualified
  HLL/KLL/ML namespaces, geography and remaining version-specific signatures need
  separate work. Recognition of an opaque result does not establish its output schema.
- Offline parser, enrichment, safety and binder tests are not live Snowflake,
  Databricks, Fabric, Athena or other remote-warehouse execution certification.

## Use enrichment

Choose the SQLGlot dialect for your project and preview the proposals:

```bash
extra --dialect spark enrich --select function_example --preview
extra --dialect tsql enrich --select function_example --preview
```

Use the command matching your SQL, replacing `function_example` with your model
name. A persistent choice can be set with `analysis.dialect` in
[`extra_project.yaml`](../configuration.md). Manifest autodetection maps
`fabricspark` to `spark` and `sqlserver` to `tsql`. Fabric Warehouse keeps its
dedicated `fabric` dialect; T-SQL examples do not automatically certify Fabric.
Likewise, Spark examples do not certify `databricks`. See
[dialect coverage](../../compatibility.md#sql-dialects).

Enrichment fills missing `data_type` values in existing writable dbt YAML model
entries. It never overwrites authored types or descriptions. Function expressions
do not inherit upstream descriptions: a transformed value need not have the same
business meaning as its input. Only unambiguous bare-column passthroughs/renames
can inherit a description. Missing YAML entries are skipped, not created.

## Verified examples

Each row is checked offline through analysis and enrichment, including YAML
writeback where a type is inferred. The SQL shape is:

```sql
SELECT <expression> AS result
FROM {{ ref('orders') }}
```

The upstream `orders` model declares `id` as `BIGINT`. Expressions using `id`
depend on that evidence; string literals and explicit casts supply their own
input types. Each result starts without an authored type or description.

| Dialect | Expression | Inferred `data_type` |
| --- | --- | --- |
| `spark` | `UPPER('abc')` | `STRING` |
| `spark` | `LENGTH('abc')` | `INT` |
| `spark` | `CONCAT('a', 'b')` | `STRING` |
| `spark` | `ABS(id)` | `BIGINT` |
| `spark` | `COALESCE(id, 0)` | `BIGINT` |
| `spark` | `COUNT(*)` | `BIGINT` |
| `spark` | `SUM(id)` | `BIGINT` |
| `spark` | `DATE_ADD(CAST('2026-01-01' AS DATE), 1)` | `DATE` |
| `spark` | `mystery_udf(id)` | unresolved |
| `tsql` | `UPPER('abc')` | `VARCHAR` |
| `tsql` | `LEN('abc')` | `INTEGER` |
| `tsql` | `CONCAT('a', 'b')` | `VARCHAR` |
| `tsql` | `ABS(id)` | `BIGINT` |
| `tsql` | `ISNULL(id, 0)` | `BIGINT` |
| `tsql` | `COUNT(*)` | `INTEGER` |
| `tsql` | `SUM(id)` | `BIGINT` |
| `tsql` | `DATEADD(day, 1, CAST('2026-01-01' AS DATE))` | `DATE` |
| `tsql` | `mystery_udf(id)` | unresolved |
| `fabric` | `isjson('{}')` | `INT` |
| `fabric` | `json_path_exists('{}', '$.a')` | `INT` |
| `databricks` | `isnull(id)` | `BOOLEAN` |
| `databricks` | `schema_of_json('{"a":1}')` | `STRING` |
| `duckdb` | `pg_typeof(id)` | `TEXT` |
| `duckdb` | `current_setting('threads')` | unresolved |
| `postgres` | `pg_typeof(id)` | unresolved |
| `postgres` | `current_setting('search_path')` | `TEXT` |
| `postgres` | `pg_backend_pid()` | `INT` |
| `postgres` | `jsonb_path_exists('{}'::jsonb, '$.a')` | `BOOLEAN` |
| `snowflake` | `get_ddl('TABLE', 't')` | `VARCHAR` |
| `snowflake` | `last_query_id()` | `VARCHAR` |
| `snowflake` | `is_role_in_session('PUBLIC')` | `BOOLEAN` |
| `bigquery` | `error('stop')` | unresolved |
| `bigquery` | `generate_range_array(RANGE(DATE '2020-01-01', DATE '2020-02-01'), INTERVAL 1 DAY)` | unresolved |
| `redshift` | `fnv_hash('abc')` | `BIGINT` |
| `redshift` | `pg_last_query_id()` | `INTEGER` |
| `trino` | `bar(0.5, 10)` | `VARCHAR` |
| `trino` | `murmur3(to_utf8('abc'))` | `VARBINARY` |
| `athena` | `format_number(123456)` | `VARCHAR` |
| `athena` | `invoker_principal()` | `VARCHAR` |

These are SQLGlot-rendered type names, not complete warehouse function signatures.
For example, `VARCHAR` does not establish a string length. Precision, scale,
nullability, implicit conversions and runtime errors need independent review.
No warehouse is executed by this function-enrichment matrix.

## Limits and unresolved results

- The shared inference path extends SQLGlot's per-call type annotations with the
  local catalogs above; there are no user-configurable UDF signatures.
- Unknown/NULL inferred types are omitted. Enrichment reports an unresolved
  property rather than writing a guessed type. `mystery_udf` above is an example
  of an unknown function, not a built-in function to install.
- Missing declared input types, ambiguous columns, unsupported SQL or opaque
  Jinja can prevent inference. Successful parsing alone is not sufficient.
- No warehouse connection, function-catalog lookup or runtime dbt macro execution
  is used to discover return types.
- Type inference does not authorize a function rewrite or establish determinism,
  SQL equivalence, execution compatibility or performance improvements.

Review with `--preview`, supply missing schema evidence or author the type in dbt
YAML when inference cannot resolve it, then run dbt/warehouse checks independently.
See the [enrichment workflow](../../guides/metadata-enrichment.md).

## Adding coverage

Keep one shared inference path rather than a parallel function system per adapter:

1. Select the explicit SQLGlot dialect and verify parsing and return-type inference
   separately, using representative argument types and declared upstream metadata.
2. Prefer existing SQLGlot behavior. For a demonstrated gap, prefer an upstream
   fix; any local special case needs a focused justification and regression test.
3. Add the demonstrated gap to its dialect catalog and executable tests. Cover YAML
   proposals, unresolved results and preservation of authored metadata, not just
   whether an expression parses.
4. Check dependency upgrades for changed inference or rendered type names. Related
   dialects need their own evidence; parser inheritance does not certify results.
5. Keep execution checks and optimizer permissions separate. Document planned
   coverage as planned until its regressions pass.

The executable examples live in
[`tests/workflows/test_function_enrichment.py`](../../../tests/workflows/test_function_enrichment.py).

<!-- BEGIN GENERATED FUNCTION INVENTORY -->
## Function implementation matrix

**3133 function names · 11 dialects**. Generated against **SQLGlot 30.29.0** and the current dbt-extra catalogs.
Official documentation snapshot: **2026-11-05**.

**S** = SQLGlot · **E** = dbt-extra · **B** = both · **×** = neither · **—** = not listed for that dialect.

These are analysis/recognition entries, not warehouse compatibility guarantees.
Inherited SQLGlot names may not execute in a dialect; **—** does not prove
warehouse incompatibility. See [scope and symbol definitions](#reading-the-matrix).
Dialect headers link to the detailed local type policies.

| SQL function | [DuckDB](duckdb.md) | [PostgreSQL](postgres.md) | [Snowflake](snowflake.md) | [BigQuery](bigquery.md) | [Spark](spark.md) | [T-SQL](tsql.md) | [Fabric](fabric.md) | [Databricks](databricks.md) | [Redshift](redshift.md) | [Trino](trino.md) | [Athena](athena.md) |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `@@CONNECTIONS` | — | — | — | — | — | × | — | — | — | — | — |
| `@@CPU_BUSY` | — | — | — | — | — | × | — | — | — | — | — |
| `@@CURSOR_ROWS` | — | — | — | — | — | × | — | — | — | — | — |
| `@@DATEFIRST` | — | — | — | — | — | × | × | — | — | — | — |
| `@@DBTS` | — | — | — | — | — | × | — | — | — | — | — |
| `@@ERROR` | — | — | — | — | — | × | × | — | — | — | — |
| `@@FETCH_STATUS` | — | — | — | — | — | × | — | — | — | — | — |
| `@@IDENTITY` | — | — | — | — | — | × | — | — | — | — | — |
| `@@IDLE` | — | — | — | — | — | × | — | — | — | — | — |
| `@@IO_BUSY` | — | — | — | — | — | × | — | — | — | — | — |
| `@@LANGID` | — | — | — | — | — | × | — | — | — | — | — |
| `@@LANGUAGE` | — | — | — | — | — | × | — | — | — | — | — |
| `@@LOCK_TIMEOUT` | — | — | — | — | — | × | — | — | — | — | — |
| `@@MAX_CONNECTIONS` | — | — | — | — | — | × | — | — | — | — | — |
| `@@MAX_PRECISION` | — | — | — | — | — | × | — | — | — | — | — |
| `@@NESTLEVEL` | — | — | — | — | — | × | — | — | — | — | — |
| `@@OPTIONS` | — | — | — | — | — | × | — | — | — | — | — |
| `@@PACKET_ERRORS` | — | — | — | — | — | × | — | — | — | — | — |
| `@@PACK_RECEIVED` | — | — | — | — | — | × | — | — | — | — | — |
| `@@PACK_SENT` | — | — | — | — | — | × | — | — | — | — | — |
| `@@PROCID` | — | — | — | — | — | × | — | — | — | — | — |
| `@@REMSERVER` | — | — | — | — | — | × | — | — | — | — | — |
| `@@ROWCOUNT` | — | — | — | — | — | × | — | — | — | — | — |
| `@@SERVERNAME` | — | — | — | — | — | × | — | — | — | — | — |
| `@@SERVICENAME` | — | — | — | — | — | × | — | — | — | — | — |
| `@@SPID` | — | — | — | — | — | × | — | — | — | — | — |
| `@@TEXTSIZE` | — | — | — | — | — | × | — | — | — | — | — |
| `@@TIMETICKS` | — | — | — | — | — | × | — | — | — | — | — |
| `@@TOTAL_ERRORS` | — | — | — | — | — | × | — | — | — | — | — |
| `@@TOTAL_READ` | — | — | — | — | — | × | — | — | — | — | — |
| `@@TOTAL_WRITE` | — | — | — | — | — | × | — | — | — | — | — |
| `@@TRANCOUNT` | — | — | — | — | — | × | × | — | — | — | — |
| `@@VERSION` | — | — | — | — | — | × | × | — | — | — | — |
| `ABBREV` | — | × | — | — | — | — | — | — | — | — | — |
| `ABS` | S | S | S | S | S | S | S | S | S | S | S |
| `ACCUMULATE` | — | — | × | — | — | — | — | — | — | — | — |
| `ACLDEFAULT` | — | × | — | — | — | — | — | — | — | — | — |
| `ACLEXPLODE` | — | × | — | — | — | — | — | — | — | — | — |
| `ACOS` | S | S | S | S | S | S | S | S | S | S | S |
| `ACOSD` | — | × | — | — | — | — | — | — | — | — | — |
| `ACOSH` | S | S | S | S | S | S | S | S | S | S | S |
| `ADD` | × | — | — | — | — | — | — | — | — | — | — |
| `ADD_MONTHS` | S | S | S | S | S | S | S | S | S | S | S |
| `AEAD.DECRYPT_BYTES` | — | — | — | × | — | — | — | — | — | — | — |
| `AEAD.DECRYPT_STRING` | — | — | — | × | — | — | — | — | — | — | — |
| `AEAD.ENCRYPT` | — | — | — | × | — | — | — | — | — | — | — |
| `AES_DECRYPT` | — | — | — | — | E | — | — | E | — | — | — |
| `AES_ENCRYPT` | — | — | — | — | E | — | — | E | — | — | — |
| `AGE` | × | × | — | — | — | — | — | — | — | — | — |
| `AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `AGGREGATE` | × | — | — | — | S | — | — | S | — | — | — |
| `AGO` | × | — | — | — | — | — | — | — | — | — | — |
| `AI_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `AI_ANALYZE_SENTIMENT` | — | — | — | — | — | × | — | × | — | — | — |
| `AI_CLASSIFY` | S | S | S | S | S | S | S | S | S | S | S |
| `AI_COMPLETE` | — | — | × | — | — | — | — | — | — | — | — |
| `AI_COUNT_TOKENS` | — | — | × | — | — | — | — | — | — | — | — |
| `AI_DECIDE` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_DETECT_ANOMALIES` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_EMBED` | S | S | S | S | S | S | S | S | S | S | S |
| `AI_ENRICH` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_EXTRACT` | — | — | × | — | — | × | — | × | — | — | — |
| `AI_FILTER` | — | — | × | — | — | — | — | — | — | — | — |
| `AI_FIX_GRAMMAR` | — | — | — | — | — | × | — | × | — | — | — |
| `AI_FORECAST` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_GEN` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_GENERATE` | S | S | S | S | S | S | S | S | S | S | S |
| `AI_GENERATE_CHUNKS` | — | — | — | — | — | × | — | — | — | — | — |
| `AI_GENERATE_EMBEDDINGS` | — | — | — | — | — | × | — | — | — | — | — |
| `AI_GENERATE_RESPONSE` | — | — | — | — | — | × | — | — | — | — | — |
| `AI_GENERATE_TEXT` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_MASK` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_MULTI_EMBED` | — | — | × | — | — | — | — | — | — | — | — |
| `AI_PARSE_DOCUMENT` | — | — | × | — | — | — | — | × | — | — | — |
| `AI_PREDICT_CLASS` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_PREDICT_VALUE` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_PREP_SEARCH` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_QUERY` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_REDACT` | — | — | × | — | — | — | — | — | — | — | — |
| `AI_SEARCH` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_SENTIMENT` | — | — | × | — | — | — | — | — | — | — | — |
| `AI_SIMILARITY` | S | S | S | S | S | S | S | S | S | S | S |
| `AI_SUMMARIZE` | — | — | × | — | — | × | — | × | — | — | — |
| `AI_SUMMARIZE_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `AI_TOP_DRIVERS` | — | — | — | — | — | — | — | × | — | — | — |
| `AI_TRANSCRIBE` | — | — | × | — | — | — | — | × | — | — | — |
| `AI_TRANSLATE` | — | — | × | — | — | × | — | × | — | — | — |
| `ALERT_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `ALIAS` | × | — | — | — | — | — | — | — | — | — | — |
| `ALL_MATCH` | — | — | — | — | — | — | — | — | — | E | E |
| `ALL_USER_NAMES` | — | — | × | — | — | — | — | — | — | — | — |
| `AND` | S | S | S | S | S | S | S | S | S | S | S |
| `ANONYMOUS_AGG_FUNC` | S | S | S | S | S | S | S | S | S | S | S |
| `ANY` | — | × | — | — | × | — | — | × | — | — | — |
| `ANY_MATCH` | — | — | — | — | — | — | — | — | — | E | E |
| `ANY_VALUE` | S | S | S | S | S | S | S | S | S | S | S |
| `APPENDS` | — | — | — | × | — | — | — | — | — | — | — |
| `APPLICATION_CALLBACK_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `APPLICATION_CONFIGURATION_VALUE_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `APPLICATION_JSON` | — | — | × | — | — | — | — | — | — | — | — |
| `APPLICATION_SPECIFICATION_STATUS_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `APPLOCK_MODE` | — | — | — | — | — | × | — | — | — | — | — |
| `APPLOCK_TEST` | — | — | — | — | — | × | — | — | — | — | — |
| `APPLY` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROXIMATE_JACCARD_INDEX` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROXIMATE_SIMILARITY` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_COUNT_DISTINCT` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_DISTINCT` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_MEDIAN` | — | — | — | — | — | × | — | — | — | — | — |
| `APPROX_MOST_FREQUENT` | — | — | — | — | — | — | — | — | — | E | × |
| `APPROX_PERCENTILE` | — | — | S | — | S | — | — | S | — | B | S |
| `APPROX_PERCENTILE_ACCUMULATE` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_PERCENTILE_COMBINE` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_PERCENTILE_CONT` | — | — | — | — | — | × | × | — | — | — | — |
| `APPROX_PERCENTILE_DISC` | — | — | — | — | — | × | × | — | — | — | — |
| `APPROX_PERCENTILE_ESTIMATE` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_QUANTILE` | B | S | S | S | S | S | S | S | S | B | S |
| `APPROX_QUANTILES` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_SET` | — | — | — | — | — | — | — | — | — | × | × |
| `APPROX_TOP_COUNT` | — | — | — | S | — | — | — | — | — | — | — |
| `APPROX_TOP_K` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_TOP_K_ACCUMULATE` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_TOP_K_COMBINE` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_TOP_K_ESTIMATE` | S | S | S | S | S | S | S | S | S | S | S |
| `APPROX_TOP_SUM` | S | S | S | S | S | S | S | S | S | S | S |
| `APP_NAME` | — | — | — | — | — | E | — | — | — | — | — |
| `ARBITRARY` | — | — | — | — | — | — | — | — | — | S | S |
| `AREA` | — | × | — | — | — | — | — | — | — | — | — |
| `ARGMAX` | S | S | S | S | S | S | S | S | S | S | S |
| `ARGMIN` | S | S | S | S | S | S | S | S | S | S | S |
| `ARG_MAX` | S | S | S | S | S | S | S | S | S | S | S |
| `ARG_MAX_NULL` | × | — | — | — | — | — | — | — | — | — | — |
| `ARG_MAX_NULLS_LAST` | × | — | — | — | — | — | — | — | — | — | — |
| `ARG_MIN` | S | S | S | S | S | S | S | S | S | S | S |
| `ARG_MIN_NULL` | × | — | — | — | — | — | — | — | — | — | — |
| `ARG_MIN_NULLS_LAST` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAYAGG` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAYS_OVERLAP` | — | — | S | — | E | — | — | × | × | × | × |
| `ARRAYS_TO_OBJECT` | — | — | × | — | — | — | — | — | — | — | — |
| `ARRAYS_ZIP` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_AGGR` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_AGGREGATE` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_ALL` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_ANY` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_APPEND` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_APPLY` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_CAT` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_COMPACT` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_CONCAT` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_CONCAT_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_CONSTRUCT` | — | — | S | — | — | — | — | — | — | — | — |
| `ARRAY_CONSTRUCT_COMPACT` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_CONSTRUCT_STRUCTURED` | — | — | × | — | — | — | — | — | — | — | — |
| `ARRAY_CONTAINED_BY` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_CONTAINS` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_CONTAINS_ALL` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_COSINE_DISTANCE` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_COSINE_SIMILARITY` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_CROSS_PRODUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_DIMS` | — | E | — | — | — | — | — | — | — | — | — |
| `ARRAY_DISTANCE` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_DISTINCT` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_DOT_PRODUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_EXCEPT` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_EXTRACT` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_FILL` | — | × | — | — | — | — | — | — | — | — | — |
| `ARRAY_FILTER` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_FIRST` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_FLATTEN` | — | — | S | — | — | — | — | — | E | — | — |
| `ARRAY_GENERATE_RANGE` | — | — | S | — | — | — | — | — | — | — | — |
| `ARRAY_GRADE_UP` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_HAS` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_HAS_ALL` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_HAS_ANY` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_HISTOGRAM` | — | — | — | — | — | — | — | — | — | E | × |
| `ARRAY_INDEXOF` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_INNER_PRODUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_INSERT` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_INTERSECT` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_INTERSECTION` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_JOIN` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_LAST` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_LENGTH` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_LOWER` | — | × | — | — | — | — | — | — | — | — | — |
| `ARRAY_MAX` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_MIN` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_NDIMS` | — | E | — | — | — | — | — | — | — | — | — |
| `ARRAY_NEGATIVE_DOT_PRODUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_NEGATIVE_INNER_PRODUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_OVERLAPS` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_POP_BACK` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_POP_FRONT` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_POSITION` | B | B | S | S | B | S | S | B | S | B | B |
| `ARRAY_POSITIONS` | — | E | — | — | — | — | — | — | × | — | — |
| `ARRAY_PREPEND` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_PUSH_BACK` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_PUSH_FRONT` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_REDUCE` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_REMOVE` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_REMOVE_AT` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_REPEAT` | — | — | × | — | E | — | — | E | — | — | — |
| `ARRAY_REPLACE` | — | × | — | — | — | — | — | — | — | — | — |
| `ARRAY_RESIZE` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_REVERSE` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_REVERSE_SORT` | S | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_SAMPLE` | — | E | — | — | — | — | — | — | — | — | — |
| `ARRAY_SELECT` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_SHUFFLE` | — | E | — | — | — | — | — | — | — | — | — |
| `ARRAY_SIZE` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_SLICE` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_SORT` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_SUM` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_TO_JSON` | — | × | — | — | — | — | — | — | — | — | — |
| `ARRAY_TO_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_TO_STRING_COMMA_DEFAULT` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_TO_TSVECTOR` | — | × | — | — | — | — | — | — | — | — | — |
| `ARRAY_TRANSFORM` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_UNION` | — | — | — | — | E | — | — | E | × | × | × |
| `ARRAY_UNION_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_UNIQUE` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_UNIQUE_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `ARRAY_UPPER` | — | × | — | — | — | — | — | — | — | — | — |
| `ARRAY_VALUE` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_WHERE` | × | — | — | — | — | — | — | — | — | — | — |
| `ARRAY_ZIP` | × | — | — | — | — | — | — | — | — | — | — |
| `ASCII` | S | S | S | S | S | S | S | S | S | S | S |
| `ASIN` | S | S | S | S | S | S | S | S | S | S | S |
| `ASIND` | — | × | — | — | — | — | — | — | — | — | — |
| `ASINH` | S | S | S | S | S | S | S | S | S | S | S |
| `ASSEMBLYPROPERTY` | — | — | — | — | — | × | — | — | — | — | — |
| `ASSERT_TRUE` | — | — | — | — | E | — | — | E | — | — | — |
| `ASYMKEYPROPERTY` | — | — | — | — | — | × | — | — | — | — | — |
| `ASYMKEY_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `AS_ARRAY` | — | — | × | — | — | — | — | — | — | — | — |
| `AS_BINARY` | — | — | × | — | — | — | — | — | — | — | — |
| `AS_BOOLEAN` | — | — | × | — | — | — | — | — | — | — | — |
| `AS_DATE` | — | — | × | — | — | — | — | — | — | — | — |
| `AS_INTEGER` | — | — | × | — | — | — | — | — | — | — | — |
| `AS_OBJECT` | — | — | × | — | — | — | — | — | — | — | — |
| `AS_TIME` | — | — | × | — | — | — | — | — | — | — | — |
| `ATAN` | S | S | S | S | S | S | S | S | S | S | S |
| `ATAN2` | S | S | S | S | S | S | S | S | S | S | S |
| `ATAN2D` | — | × | — | — | — | — | — | — | — | — | — |
| `ATAND` | — | × | — | — | — | — | — | — | — | — | — |
| `ATANH` | S | S | S | S | S | S | S | S | S | S | S |
| `ATN2` | — | — | — | — | — | S | S | — | — | — | — |
| `AT_TIMEZONE` | — | — | — | — | — | — | — | — | — | × | × |
| `AUTOMATIC_CLUSTERING_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `AUTO_REFRESH_REGISTRATION_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `AVAILABLE_LISTINGS` | — | — | × | — | — | — | — | — | — | — | — |
| `AVAILABLE_LISTING_REFRESH_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `AVG` | B | B | S | S | B | B | B | B | B | S | S |
| `A_I_FORECAST` | S | S | S | S | S | S | S | S | S | S | S |
| `BAG_OF_WORDS` | — | — | — | × | — | — | — | — | — | — | — |
| `BAR` | × | — | — | — | — | — | — | — | — | E | × |
| `BASE64` | × | — | — | — | S | — | — | S | — | — | — |
| `BASE64_DECODE` | — | — | — | — | — | × | × | — | — | — | — |
| `BASE64_DECODE_BINARY` | S | S | S | S | S | S | S | S | S | S | S |
| `BASE64_DECODE_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `BASE64_ENCODE` | S | S | S | S | S | S | S | S | S | S | S |
| `BETA_CDF` | — | — | — | — | — | — | — | — | — | × | × |
| `BIGINT` | — | — | — | — | E | — | — | E | — | — | — |
| `BIN` | × | — | — | — | E | — | — | E | — | — | — |
| `BINARY` | — | — | — | — | E | — | — | E | — | — | — |
| `BINARY_CHECKSUM` | — | — | — | — | — | E | × | — | — | — | — |
| `BIND_VALUES` | — | — | × | — | — | — | — | — | — | — | — |
| `BING_TILE` | — | — | — | — | — | — | — | — | — | × | × |
| `BING_TILES_AROUND` | — | — | — | — | — | — | — | — | — | × | × |
| `BING_TILE_AT` | — | — | — | — | — | — | — | — | — | × | × |
| `BING_TILE_COORDINATES` | — | — | — | — | — | — | — | — | — | × | × |
| `BING_TILE_POLYGON` | — | — | — | — | — | — | — | — | — | × | × |
| `BING_TILE_QUADKEY` | — | — | — | — | — | — | — | — | — | × | × |
| `BING_TILE_ZOOM_LEVEL` | — | — | — | — | — | — | — | — | — | × | × |
| `BINOM` | × | — | — | — | — | — | — | — | — | — | — |
| `BITAND` | — | — | S | — | — | — | — | — | — | — | — |
| `BITANDAGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BITAND_AGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BITMAP_ABSOLUTE_POSITION` | — | — | × | — | — | — | — | — | — | — | — |
| `BITMAP_AND` | — | — | × | — | — | — | — | — | — | — | — |
| `BITMAP_AND_AGG` | — | — | × | — | — | — | — | E | — | — | — |
| `BITMAP_BIT_POSITION` | S | S | S | S | S | S | S | S | S | S | S |
| `BITMAP_BUCKET_NUMBER` | S | S | S | S | S | S | S | S | S | S | S |
| `BITMAP_CONSTRUCT_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `BITMAP_COUNT` | S | S | S | S | S | S | S | S | S | S | S |
| `BITMAP_OR` | — | — | × | — | — | — | — | — | — | — | — |
| `BITMAP_OR_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `BITMAP_TO_ARRAY` | — | — | × | — | — | — | — | — | — | — | — |
| `BITNOT` | — | — | S | — | — | — | — | — | — | — | — |
| `BITOR` | — | — | S | — | — | — | — | — | — | — | — |
| `BITORAGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BITOR_AGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BITSHIFTLEFT` | — | — | S | — | — | — | — | — | — | — | — |
| `BITSHIFTRIGHT` | — | — | S | — | — | — | — | — | — | — | — |
| `BITSTRING` | × | — | — | — | — | — | — | — | — | — | — |
| `BITSTRING_AGG` | × | — | — | — | — | — | — | — | — | — | — |
| `BITWISE_AND` | — | — | — | — | — | — | — | — | — | S | S |
| `BITWISE_AND_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `BITWISE_COUNT` | S | S | S | S | S | S | S | S | S | S | S |
| `BITWISE_LEFT_SHIFT` | — | — | — | — | — | — | — | — | — | × | × |
| `BITWISE_NOT` | — | — | — | — | — | — | — | — | — | S | S |
| `BITWISE_OR` | — | — | — | — | — | — | — | — | — | S | S |
| `BITWISE_OR_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `BITWISE_RIGHT_SHIFT` | — | — | — | — | — | — | — | — | — | × | × |
| `BITWISE_RIGHT_SHIFT_ARITHMETIC` | — | — | — | — | — | — | — | — | — | × | × |
| `BITWISE_XOR` | — | — | — | — | — | — | — | — | — | S | S |
| `BITWISE_XOR_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `BITXOR` | — | — | S | — | — | — | — | — | — | — | — |
| `BITXORAGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BITXOR_AGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BIT_AND` | S | S | S | S | S | — | — | S | S | — | — |
| `BIT_ANDAGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BIT_AND_AGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BIT_COUNT` | × | × | — | S | S | E | E | S | — | × | × |
| `BIT_GET` | — | — | — | — | S | — | — | S | — | — | — |
| `BIT_LENGTH` | S | S | S | S | S | S | S | S | S | S | S |
| `BIT_NOT` | — | — | S | — | — | — | — | — | — | — | — |
| `BIT_OR` | S | S | S | S | S | — | — | S | S | — | — |
| `BIT_ORAGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BIT_OR_AGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BIT_POSITION` | × | — | — | — | — | — | — | — | — | — | — |
| `BIT_REVERSE` | — | — | — | — | — | — | — | × | — | — | — |
| `BIT_SHIFTLEFT` | — | — | S | — | — | — | — | — | — | — | — |
| `BIT_SHIFTRIGHT` | — | — | S | — | — | — | — | — | — | — | — |
| `BIT_XOR` | S | S | S | S | S | — | — | S | S | — | — |
| `BIT_XORAGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BIT_XOR_AGG` | — | — | S | — | — | — | — | — | — | — | — |
| `BOOL` | — | — | — | S | — | — | — | — | — | — | — |
| `BOOLAND` | S | S | S | S | S | S | S | S | S | S | S |
| `BOOLAND_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `BOOLEAN` | — | — | — | — | S | — | — | S | — | — | — |
| `BOOLNOT` | S | S | S | S | S | S | S | S | S | S | S |
| `BOOLOR` | S | S | S | S | S | S | S | S | S | S | S |
| `BOOLOR_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `BOOLXOR` | — | — | S | — | — | — | — | — | — | — | — |
| `BOOLXOR_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `BOOL_AND` | S | S | S | S | S | S | S | S | S | S | S |
| `BOOL_OR` | S | S | S | S | S | S | S | S | S | S | S |
| `BOUND_BOX` | — | × | — | — | — | — | — | — | — | — | — |
| `BOX` | — | × | — | — | — | — | — | — | — | — | — |
| `BPCHARCMP` | — | — | — | — | — | — | — | — | × | — | — |
| `BRIN_DESUMMARIZE_RANGE` | — | × | — | — | — | — | — | — | — | — | — |
| `BRIN_SUMMARIZE_NEW_VALUES` | — | × | — | — | — | — | — | — | — | — | — |
| `BRIN_SUMMARIZE_RANGE` | — | × | — | — | — | — | — | — | — | — | — |
| `BROADCAST` | — | × | — | — | S | — | — | S | — | — | — |
| `BROADCASTJOIN` | — | — | — | — | S | — | — | S | — | — | — |
| `BROUND` | — | — | — | — | E | — | — | E | — | — | — |
| `BTRIM` | — | S | — | — | E | — | — | E | S | — | — |
| `BTTEXT_PATTERN_CMP` | — | — | — | — | — | — | — | — | × | — | — |
| `BUILD_SCOPED_FILE_URL` | — | — | × | — | — | — | — | — | — | — | — |
| `BUILD_STAGE_FILE_URL` | — | — | × | — | — | — | — | — | — | — | — |
| `BYTE_LENGTH` | S | S | S | S | S | S | S | S | S | S | S |
| `CAN_CAST_IMPLICITLY` | E | — | — | — | — | — | — | — | — | — | — |
| `CAN_JSON_PARSE` | — | — | — | — | — | — | — | — | E | — | — |
| `CARDINALITY` | × | E | — | — | × | — | — | × | — | S | S |
| `CASE` | S | S | S | S | S | S | S | S | S | S | S |
| `CASEFOLD` | — | × | — | — | — | — | — | — | — | — | — |
| `CAST` | S | S | S | S | S | S | S | S | S | S | S |
| `CAST_TO_STR_TYPE` | S | S | S | S | S | S | S | S | S | S | S |
| `CBRT` | S | S | S | S | S | S | S | S | S | S | S |
| `CEIL` | S | S | S | S | S | S | S | S | S | S | S |
| `CEILING` | S | S | S | S | S | S | S | S | S | S | S |
| `CENTER` | — | × | — | — | — | — | — | — | — | — | — |
| `CENTURY` | × | — | — | — | — | — | — | — | — | — | — |
| `CERTENCODED` | — | — | — | — | — | × | — | — | — | — | — |
| `CERTPRIVATEKEY` | — | — | — | — | — | × | — | — | — | — | — |
| `CERTPROPERTY` | — | — | — | — | — | × | — | — | — | — | — |
| `CERT_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `CHANGES` | — | — | — | × | — | — | — | — | — | — | — |
| `CHANGE_QUERY_PRIORITY` | — | — | — | — | — | — | — | — | × | — | — |
| `CHANGE_SESSION_PRIORITY` | — | — | — | — | — | — | — | — | × | — | — |
| `CHANGE_USER_PRIORITY` | — | — | — | — | — | — | — | — | × | — | — |
| `CHAR` | S | S | S | S | S | S | S | S | S | S | S |
| `CHAR2HEXINT` | — | — | — | — | — | — | — | — | — | × | × |
| `CHARACTER_LENGTH` | S | S | S | S | S | S | S | S | S | S | S |
| `CHARINDEX` | S | S | S | S | S | S | S | S | S | S | S |
| `CHAR_LENGTH` | S | S | S | S | S | S | S | S | S | S | S |
| `CHECKPOINT` | × | — | — | — | — | — | — | — | — | — | — |
| `CHECKSUM` | — | — | — | — | — | E | E | — | × | E | E |
| `CHECKSUM_AGG` | — | — | — | — | — | E | E | — | — | — | — |
| `CHECK_JSON` | S | S | S | S | S | S | S | S | S | S | S |
| `CHECK_XML` | S | S | S | S | S | S | S | S | S | S | S |
| `CHR` | S | S | S | S | S | S | S | S | S | S | S |
| `CIRCLE` | — | × | — | — | — | — | — | — | — | — | — |
| `CITY_HASH64` | S | S | S | S | S | S | S | S | S | S | S |
| `CLASSIFIER` | — | — | — | — | — | — | — | × | — | × | — |
| `CLASSIFY` | — | — | — | — | — | — | — | — | — | × | × |
| `CLOCK_TIMESTAMP` | — | E | — | — | — | — | — | — | — | — | — |
| `CLOUD_FILES_STATE` | — | — | — | — | — | — | — | × | — | — | — |
| `COALESCE` | S | S | S | S | S | S | S | S | S | S | S |
| `CODEPOINT` | — | — | — | — | — | — | — | — | — | × | × |
| `CODE_POINTS_TO_BYTES` | S | S | S | S | S | S | S | S | S | S | S |
| `CODE_POINTS_TO_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `COLLATE` | S | S | S | S | S | S | S | S | S | S | S |
| `COLLATION` | S | S | S | S | S | S | S | S | S | S | S |
| `COLLATIONS` | — | — | — | — | — | — | — | × | — | — | — |
| `COLLECT_LIST` | — | — | — | — | S | — | — | S | — | — | — |
| `COLLECT_SET` | — | — | — | — | S | — | — | S | — | — | — |
| `COLOR` | — | — | — | — | — | — | — | — | — | × | × |
| `COLUMNPROPERTY` | — | — | — | — | — | E | × | — | — | — | — |
| `COLUMNS` | S | S | S | S | S | S | S | S | S | S | S |
| `COLUMNS_UPDATED` | — | — | — | — | — | × | — | — | — | — | — |
| `COL_DESCRIPTION` | — | × | — | — | — | — | — | — | — | — | — |
| `COL_LENGTH` | — | — | — | — | — | E | — | — | — | — | — |
| `COL_NAME` | — | — | — | — | — | E | × | — | — | — | — |
| `COMBINATIONS` | — | — | — | — | — | — | — | — | — | × | × |
| `COMBINED_AGG_FUNC` | S | S | S | S | S | S | S | S | S | S | S |
| `COMBINED_PARAMETERIZED_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `COMPLETE` | — | — | × | — | — | — | — | — | — | — | — |
| `COMPLETE_TASK_GRAPHS` | — | — | × | — | — | — | — | — | — | — | — |
| `COMPRESS` | S | S | S | S | S | S | S | S | S | S | S |
| `CONCAT` | S | S | S | S | S | S | S | S | S | S | S |
| `CONCAT_WS` | S | S | S | S | S | S | S | S | S | S | S |
| `CONDITIONAL_CHANGE_EVENT` | — | — | × | — | — | — | — | — | — | — | — |
| `CONDITIONAL_TRUE_EVENT` | — | — | × | — | — | — | — | — | — | — | — |
| `CONNECTIONPROPERTY` | — | — | — | — | — | E | — | — | — | — | — |
| `CONNECT_BY_ROOT` | S | S | S | S | S | S | S | S | S | S | S |
| `CONSTANT_OR_NULL` | × | — | — | — | — | — | — | — | — | — | — |
| `CONTAINS` | S | S | S | S | S | S | S | S | S | S | S |
| `CONTAINS_SEQUENCE` | — | — | — | — | — | — | — | — | — | E | E |
| `CONTAINS_SUBSTR` | — | — | — | S | — | — | — | — | — | — | — |
| `CONTEXT_INFO` | — | — | — | — | — | E | — | — | — | — | — |
| `CONV` | — | — | — | — | E | — | — | E | — | — | — |
| `CONVERT` | S | S | S | S | S | S | S | S | S | S | S |
| `CONVERT_FROM` | — | × | — | — | — | — | — | — | — | — | — |
| `CONVERT_TIMEZONE` | S | S | S | S | S | S | S | S | S | S | S |
| `CONVERT_TO` | — | × | — | — | — | — | — | — | — | — | — |
| `CONVERT_TO_CHARSET` | S | S | S | S | S | S | S | S | S | S | S |
| `CONVEX_HULL_AGG` | — | — | — | — | — | — | — | — | — | × | × |
| `COPY_FILE` | — | — | — | — | — | — | — | × | — | — | — |
| `COPY_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `CORR` | S | S | S | S | S | S | S | S | S | S | S |
| `CORTEX_SEARCH_BATCH` | — | — | × | — | — | — | — | — | — | — | — |
| `CORTEX_SEARCH_DATA_SCAN` | — | — | × | — | — | — | — | — | — | — | — |
| `CORTEX_SEARCH_REFRESH_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `COS` | S | S | S | S | S | S | S | S | S | S | S |
| `COSD` | — | × | — | — | — | — | — | — | — | — | — |
| `COSH` | S | S | S | S | S | S | S | S | S | S | S |
| `COSINE_DISTANCE` | S | S | S | S | S | S | S | S | S | S | S |
| `COSINE_SIMILARITY` | — | — | — | — | — | — | — | — | — | × | × |
| `COT` | S | S | S | S | S | S | S | S | S | S | S |
| `COTD` | — | × | — | — | — | — | — | — | — | — | — |
| `COTH` | S | S | S | S | S | S | S | S | S | S | S |
| `COUNT` | S | S | S | S | S | S | S | S | S | S | S |
| `COUNTER_DIFF` | — | — | — | — | — | — | — | × | — | — | — |
| `COUNTIF` | S | S | S | S | S | S | S | S | S | S | S |
| `COUNT_BIG` | — | — | — | — | — | S | S | — | — | — | — |
| `COUNT_IF` | S | S | S | S | S | S | S | S | S | S | S |
| `COUNT_MIN_SKETCH` | — | — | — | — | E | — | — | E | — | — | — |
| `COVAR_POP` | S | S | S | S | S | S | S | S | S | S | S |
| `COVAR_SAMP` | S | S | S | S | S | S | S | S | S | S | S |
| `CRC32` | — | × | — | — | × | — | — | × | × | × | × |
| `CRC32C` | — | × | — | — | — | — | — | — | — | — | — |
| `CREATE_FILE` | — | — | — | — | — | — | — | × | — | — | — |
| `CREATE_SORT_KEY` | E | — | — | — | — | — | — | — | — | — | — |
| `CRYPT_GEN_RANDOM` | — | — | — | — | — | × | — | — | — | — | — |
| `CSC` | S | S | S | S | S | S | S | S | S | S | S |
| `CSCH` | S | S | S | S | S | S | S | S | S | S | S |
| `CUBE` | — | — | — | — | — | — | — | × | — | — | — |
| `CUME_DIST` | S | S | S | S | S | S | S | S | S | S | S |
| `CUMULATIVE_PRIVACY_LOSSES` | — | — | × | — | — | — | — | — | — | — | — |
| `CURDATE` | — | — | — | — | S | — | — | S | — | — | — |
| `CURRENT_ACCOUNT` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_ACCOUNT_NAME` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_AVAILABLE_ROLES` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_AWS_ACCOUNT` | — | — | — | — | — | — | — | — | × | — | — |
| `CURRENT_CATALOG` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_CLIENT` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_DATABASE` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_DATETIME` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_GROUPS` | — | — | — | — | — | — | — | — | — | × | × |
| `CURRENT_IP_ADDRESS` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_LOCALTIME` | × | — | — | — | — | — | — | — | — | — | — |
| `CURRENT_LOCALTIMESTAMP` | S | — | — | — | — | — | — | — | — | — | — |
| `CURRENT_METASTORE` | — | — | — | — | — | — | — | × | — | — | — |
| `CURRENT_NAMESPACE` | — | — | — | — | — | — | — | — | × | — | — |
| `CURRENT_OAUTH_CUSTOM_IDENTITY_CLAIM` | — | — | — | — | — | — | — | × | — | — | — |
| `CURRENT_ORGANIZATION_NAME` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_ORGANIZATION_USER` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_PATH` | — | — | — | — | — | — | — | × | — | — | — |
| `CURRENT_QUERY` | E | × | — | — | — | — | — | — | — | — | — |
| `CURRENT_QUERY_ID` | × | — | — | — | — | — | — | — | — | — | — |
| `CURRENT_RECIPIENT` | — | — | — | — | — | — | — | × | — | — | — |
| `CURRENT_REGION` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_REQUEST_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `CURRENT_ROLE` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_ROLE_TYPE` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_SCHEMA` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_SCHEMAS` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_SECONDARY_ROLES` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_SESSION` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_SESSION_ARN` | — | — | — | — | — | — | — | — | × | — | — |
| `CURRENT_SETTING` | E | E | — | — | — | — | — | — | × | — | — |
| `CURRENT_SNAPSHOT_VERSION` | — | — | — | — | — | — | — | × | — | — | — |
| `CURRENT_STATEMENT` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_TASK_GRAPHS` | — | — | × | — | — | — | — | — | — | — | — |
| `CURRENT_TIME` | B | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_TIMESTAMP` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_TIMESTAMP_L_T_Z` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_TIMEZONE` | S | S | S | S | S | S | S | S | S | B | S |
| `CURRENT_TIMEZONE_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `CURRENT_TRANSACTION` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_TRANSACTION_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `CURRENT_USER` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_USER_ID` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_VERSION` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRENT_WAREHOUSE` | S | S | S | S | S | S | S | S | S | S | S |
| `CURRVAL` | × | × | — | — | — | — | — | — | — | — | — |
| `CURSOR_STATUS` | — | — | — | — | — | E | — | — | — | — | — |
| `CURSOR_TO_XML` | — | × | — | — | — | — | — | — | — | — | — |
| `CURSOR_TO_XMLSCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `DAMERAU_LEVENSHTEIN` | × | — | — | — | — | — | — | — | — | — | — |
| `DATABASEPROPERTYEX` | — | — | — | — | — | E | — | — | — | — | — |
| `DATABASE_PRINCIPAL_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `DATABASE_REFRESH_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `DATABASE_REPLICATION_USAGE_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `DATABASE_STORAGE_USAGE_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `DATABASE_TO_XML` | — | × | — | — | — | — | — | — | — | — | — |
| `DATABASE_TO_XMLSCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `DATABASE_TO_XML_AND_XMLSCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `DATALENGTH` | — | — | — | — | — | × | — | — | — | — | — |
| `DATASKETCHES_HLL` | — | — | × | — | — | — | — | — | — | — | — |
| `DATASKETCHES_HLL_ACCUMULATE` | — | — | × | — | — | — | — | — | — | — | — |
| `DATASKETCHES_HLL_COMBINE` | — | — | × | — | — | — | — | — | — | — | — |
| `DATASKETCHES_HLL_ESTIMATE` | — | — | × | — | — | — | — | — | — | — | — |
| `DATA_METRIC_FUNCTION_EXPECTATIONS` | — | — | × | — | — | — | — | — | — | — | — |
| `DATA_METRIC_FUNCTION_REFERENCES` | — | — | × | — | — | — | — | — | — | — | — |
| `DATA_QUALITY_MONITORING_EXPECTATION_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `DATA_QUALITY_MONITORING_RESULTS` | — | — | × | — | — | — | — | — | — | — | — |
| `DATA_SKIPPING_SUMMARY` | — | — | — | — | — | — | — | × | — | — | — |
| `DATA_TRANSFER_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `DATEADD` | — | — | S | — | S | S | S | S | S | — | — |
| `DATEDIFF` | S | S | S | S | S | S | S | S | S | S | S |
| `DATEDIFF_BIG` | — | — | — | — | — | S | S | — | — | — | — |
| `DATEFROMPARTS` | S | S | S | S | S | S | S | S | S | S | S |
| `DATENAME` | — | — | — | — | — | S | S | — | — | — | — |
| `DATEPART` | × | — | — | — | E | S | S | — | — | — | — |
| `DATETIME` | S | S | S | S | S | S | S | S | S | S | S |
| `DATETIME2FROMPARTS` | — | — | — | — | — | E | × | — | — | — | — |
| `DATETIMEFROMPARTS` | — | — | — | — | — | S | S | — | — | — | — |
| `DATETIMEOFFSETFROMPARTS` | — | — | — | — | — | E | × | — | — | — | — |
| `DATETIME_ADD` | S | S | S | S | S | S | S | S | S | S | S |
| `DATETIME_BUCKET` | — | — | — | E | — | — | — | — | — | — | — |
| `DATETIME_DIFF` | S | S | S | S | S | S | S | S | S | S | S |
| `DATETIME_SUB` | S | S | S | S | S | S | S | S | S | S | S |
| `DATETIME_TRUNC` | S | S | S | S | S | S | S | S | S | S | S |
| `DATETRUNC` | S | — | — | — | — | S | S | — | — | — | — |
| `DATE_ADD` | S | S | S | S | S | S | S | S | S | S | S |
| `DATE_BIN` | S | S | S | S | S | S | S | S | S | S | S |
| `DATE_BUCKET` | — | — | — | E | — | E | × | — | — | — | — |
| `DATE_CMP` | — | — | — | — | — | — | — | — | × | — | — |
| `DATE_CMP_TIMESTAMP` | — | — | — | — | — | — | — | — | × | — | — |
| `DATE_CMP_TIMESTAMPTZ` | — | — | — | — | — | — | — | — | × | — | — |
| `DATE_DIFF` | S | S | S | S | S | S | S | S | S | S | S |
| `DATE_FORMAT` | — | — | — | — | S | — | — | S | — | S | S |
| `DATE_FROM_PARTS` | S | S | S | S | S | S | S | S | S | S | S |
| `DATE_FROM_UNIX_DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `DATE_PARSE` | — | — | — | — | — | — | — | — | — | S | S |
| `DATE_PART` | × | S | S | — | E | — | — | E | S | — | — |
| `DATE_PART_YEAR` | — | — | — | — | — | — | — | — | × | — | — |
| `DATE_STR_TO_DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `DATE_SUB` | × | S | S | S | S | S | S | S | S | S | S |
| `DATE_SUBTRACT` | — | × | — | — | — | — | — | — | — | — | — |
| `DATE_TO_DATE_STR` | S | S | S | S | S | S | S | S | S | S | S |
| `DATE_TO_DI` | S | S | S | S | S | S | S | S | S | S | S |
| `DATE_TRUNC` | S | S | S | S | S | S | S | S | S | S | S |
| `DAY` | S | S | S | S | S | S | S | S | S | S | S |
| `DAYNAME` | S | S | S | S | S | S | S | S | S | S | S |
| `DAYOFMONTH` | S | S | S | S | S | S | S | S | S | S | S |
| `DAYOFWEEK` | S | S | S | S | S | S | S | S | S | S | S |
| `DAYOFWEEKISO` | — | — | S | — | — | — | — | — | — | — | — |
| `DAYOFWEEK_ISO` | S | S | S | S | S | S | S | S | S | S | S |
| `DAYOFYEAR` | S | S | S | S | S | S | S | S | S | S | S |
| `DAYS_IN_MONTH` | × | — | — | — | — | — | — | — | — | — | — |
| `DAY_OF_MONTH` | S | S | S | S | S | S | S | S | S | S | S |
| `DAY_OF_WEEK` | S | S | S | S | S | S | S | S | S | S | S |
| `DAY_OF_YEAR` | S | S | S | S | S | S | S | S | S | S | S |
| `DBT_PROJECT_EXECUTION_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `DB_COLLATION` | — | — | — | — | — | — | — | — | × | — | — |
| `DB_ID` | — | — | — | — | — | E | × | — | — | — | — |
| `DB_NAME` | — | — | — | — | — | E | × | — | — | — | — |
| `DECADE` | × | — | — | — | — | — | — | — | — | — | — |
| `DECIMAL` | — | — | — | — | E | — | — | E | — | — | — |
| `DECIMAL_AVERAGE` | × | — | — | — | — | — | — | — | — | — | — |
| `DECIMAL_DIVISION` | × | — | — | — | — | — | — | — | — | — | — |
| `DECIMAL_PRECISION` | — | — | — | — | — | — | — | — | × | — | — |
| `DECIMAL_SCALE` | — | — | — | — | — | — | — | — | × | — | — |
| `DECODE` | S | S | S | S | S | S | S | S | S | S | S |
| `DECODE_CASE` | S | S | S | S | S | S | S | S | S | S | S |
| `DECOMPRESS` | — | — | — | — | — | E | × | — | — | — | — |
| `DECOMPRESS_BINARY` | S | S | S | S | S | S | S | S | S | S | S |
| `DECOMPRESS_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `DECRYPT` | S | S | S | S | S | S | S | S | S | S | S |
| `DECRYPTBYASYMKEY` | — | — | — | — | — | × | — | — | — | — | — |
| `DECRYPTBYCERT` | — | — | — | — | — | × | — | — | — | — | — |
| `DECRYPTBYKEY` | — | — | — | — | — | × | — | — | — | — | — |
| `DECRYPTBYKEYAUTOASYMKEY` | — | — | — | — | — | × | — | — | — | — | — |
| `DECRYPTBYKEYAUTOCERT` | — | — | — | — | — | × | — | — | — | — | — |
| `DECRYPTBYPASSPHRASE` | — | — | — | — | — | × | — | — | — | — | — |
| `DECRYPT_RAW` | S | S | S | S | S | S | S | S | S | S | S |
| `DEFAULT_IAM_ROLE` | — | — | — | — | — | — | — | — | × | — | — |
| `DEGREES` | S | S | S | S | S | S | S | S | S | S | S |
| `DENSE_RANK` | S | S | S | S | S | S | S | S | S | S | S |
| `DESTINATION_NODE_ID` | — | — | — | × | — | — | — | — | — | — | — |
| `DETERMINISTIC_DECRYPT_BYTES` | — | — | — | × | — | — | — | — | — | — | — |
| `DETERMINISTIC_DECRYPT_STRING` | — | — | — | × | — | — | — | — | — | — | — |
| `DETERMINISTIC_ENCRYPT` | — | — | — | × | — | — | — | — | — | — | — |
| `DEXP` | — | — | — | — | — | — | — | — | × | — | — |
| `DIAGONAL` | — | × | — | — | — | — | — | — | — | — | — |
| `DIAMETER` | — | × | — | — | — | — | — | — | — | — | — |
| `DIFFERENCE` | — | — | — | — | — | E | E | — | × | — | — |
| `DIRECTORY` | — | — | S | — | — | — | — | — | — | — | — |
| `DIV` | — | S | — | S | S | — | — | S | S | — | — |
| `DIV0` | — | — | S | — | — | — | — | — | — | — | — |
| `DIV0NULL` | — | — | S | — | — | — | — | — | — | — | — |
| `DIVIDE` | × | — | — | — | — | — | — | — | — | — | — |
| `DI_TO_DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `DLOG1` | — | — | — | — | — | — | — | — | × | — | — |
| `DLOG10` | — | — | — | — | — | — | — | — | × | — | — |
| `DLP_DETERMINISTIC_DECRYPT` | — | — | — | × | — | — | — | — | — | — | — |
| `DLP_DETERMINISTIC_ENCRYPT` | — | — | — | × | — | — | — | — | — | — | — |
| `DLP_KEY_CHAIN` | — | — | — | × | — | — | — | — | — | — | — |
| `DOT_PRODUCT` | S | S | S | S | S | S | S | S | S | S | S |
| `DOUBLE` | — | — | — | — | S | — | — | S | — | — | — |
| `DOW` | — | — | — | — | — | — | — | — | — | S | S |
| `DOY` | — | — | — | — | — | — | — | — | — | S | S |
| `DP_INTERVAL_HIGH` | — | — | × | — | — | — | — | — | — | — | — |
| `DP_INTERVAL_LOW` | — | — | × | — | — | — | — | — | — | — | — |
| `DUCKDB_FORMAT_SQL` | × | — | — | — | — | — | — | — | — | — | — |
| `DYNAMIC_IDENTIFIER` | S | S | S | S | S | S | S | S | S | S | S |
| `DYNAMIC_TABLES` | — | — | × | — | — | — | — | — | — | — | — |
| `DYNAMIC_TABLE_GRAPH_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `DYNAMIC_TABLE_REFRESH_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `E` | — | — | — | — | E | — | — | E | — | × | × |
| `EDGES` | — | — | — | × | — | — | — | — | — | — | — |
| `EDGE_ID_FROM_PARTS` | — | — | — | — | — | × | — | — | — | — | — |
| `EDITDIST3` | S | — | — | — | — | — | — | — | — | — | — |
| `EDITDISTANCE` | — | — | S | — | — | — | — | — | — | — | — |
| `EDIT_DISTANCE` | — | — | — | S | — | × | × | — | — | — | — |
| `EDIT_DISTANCE_SIMILARITY` | — | — | — | — | — | × | × | — | — | — | — |
| `ELEMENT_AT` | × | — | — | — | S | — | — | S | — | S | S |
| `ELEMENT_ID` | — | — | — | × | — | — | — | — | — | — | — |
| `ELT` | S | S | S | S | S | S | S | S | S | S | S |
| `EMAIL_INTEGRATION_CONFIG` | — | — | × | — | — | — | — | — | — | — | — |
| `EMBED` | — | — | — | S | — | — | — | — | — | — | — |
| `EMPTY_APPROX_SET` | — | — | — | — | — | — | — | — | — | × | × |
| `ENCODE` | S | S | S | S | S | S | S | S | S | S | S |
| `ENCRYPT` | S | S | S | S | S | S | S | S | S | S | S |
| `ENCRYPTBYASYMKEY` | — | — | — | — | — | × | — | — | — | — | — |
| `ENCRYPTBYCERT` | — | — | — | — | — | × | — | — | — | — | — |
| `ENCRYPTBYKEY` | — | — | — | — | — | × | — | — | — | — | — |
| `ENCRYPTBYPASSPHRASE` | — | — | — | — | — | × | — | — | — | — | — |
| `ENCRYPT_RAW` | S | S | S | S | S | S | S | S | S | S | S |
| `ENDSWITH` | S | S | S | S | S | S | S | S | S | S | S |
| `ENDS_WITH` | S | S | S | S | S | S | S | S | S | S | S |
| `ENTROPY` | × | — | — | — | — | — | — | — | — | — | — |
| `ENUM_CODE` | × | — | — | — | — | — | — | — | — | — | — |
| `ENUM_FIRST` | × | × | — | — | — | — | — | — | — | — | — |
| `ENUM_LAST` | × | × | — | — | — | — | — | — | — | — | — |
| `ENUM_RANGE` | × | × | — | — | — | — | — | — | — | — | — |
| `ENUM_RANGE_BOUNDARY` | × | — | — | — | — | — | — | — | — | — | — |
| `EOMONTH` | — | — | — | — | — | S | S | — | — | — | — |
| `EPOCH` | S | — | — | — | — | — | — | — | — | — | — |
| `EPOCH_MS` | S | — | — | — | — | — | — | — | — | — | — |
| `EPOCH_NS` | × | — | — | — | — | — | — | — | — | — | — |
| `EPOCH_US` | × | — | — | — | — | — | — | — | — | — | — |
| `EQUAL_NULL` | S | S | S | S | S | S | S | S | S | S | S |
| `EQUI_WIDTH_BINS` | × | — | — | — | — | — | — | — | — | — | — |
| `ERA` | × | — | — | — | — | — | — | — | — | — | — |
| `ERF` | — | × | — | — | — | — | — | — | — | — | — |
| `ERFC` | — | × | — | — | — | — | — | — | — | — | — |
| `ERROR` | E | — | — | E | — | — | — | — | — | — | — |
| `ERROR_LINE` | — | — | — | — | — | E | — | — | — | — | — |
| `ERROR_MESSAGE` | — | — | — | — | — | E | × | — | — | — | — |
| `ERROR_NUMBER` | — | — | — | — | — | E | × | — | — | — | — |
| `ERROR_PROCEDURE` | — | — | — | — | — | E | × | — | — | — | — |
| `ERROR_SEVERITY` | — | — | — | — | — | E | × | — | — | — | — |
| `ERROR_STATE` | — | — | — | — | — | E | × | — | — | — | — |
| `ESTIMATE_HYBRID_TABLE_STORAGE_USAGE` | — | — | × | — | — | — | — | — | — | — | — |
| `ESTIMATE_REMAINING_DP_AGGREGATES` | — | — | × | — | — | — | — | — | — | — | — |
| `EUCLIDEAN_DISTANCE` | S | S | S | S | S | S | S | S | S | S | S |
| `EVEN` | × | — | — | — | — | — | — | — | — | — | — |
| `EVENTDATA` | — | — | — | — | — | × | — | — | — | — | — |
| `EVENT_LOG` | — | — | — | — | — | — | — | × | — | — | — |
| `EVERY` | — | × | — | — | E | — | — | E | — | × | × |
| `EXCLUDE_COLUMNS` | — | — | — | — | — | — | — | — | — | — | × |
| `EXECUTE_AI_EVALUATION` | — | — | × | — | — | — | — | — | — | — | — |
| `EXISTS` | S | S | S | S | S | S | S | S | S | S | S |
| `EXP` | S | S | S | S | S | S | S | S | S | S | S |
| `EXPLAIN_GRANTABLE_PRIVILEGES` | — | — | × | — | — | — | — | — | — | — | — |
| `EXPLAIN_JSON` | — | — | × | — | — | — | — | — | — | — | — |
| `EXPLAIN_MODEL` | — | — | — | — | — | — | — | — | × | — | — |
| `EXPLAIN_PRIVILEGES` | — | — | × | — | — | — | — | — | — | — | — |
| `EXPLODE` | S | S | S | S | S | S | S | S | S | S | S |
| `EXPLODE_OUTER` | S | S | S | S | S | S | S | S | S | S | S |
| `EXPLODING_GENERATE_SERIES` | S | S | S | S | S | S | S | S | S | S | S |
| `EXPM1` | — | — | — | — | E | — | — | E | — | — | — |
| `EXTERNAL_FUNCTIONS_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `EXTERNAL_OBJECT_TRANSFORM` | — | — | — | × | — | — | — | — | — | — | — |
| `EXTERNAL_QUERY` | — | — | — | × | — | — | — | — | — | — | — |
| `EXTERNAL_TABLE_FILES` | — | — | × | — | — | — | — | — | — | — | — |
| `EXTERNAL_TABLE_FILE_REGISTRATION_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `EXTRACT` | S | S | S | S | S | S | S | S | S | S | S |
| `EXTRACT_SEMANTIC_CATEGORIES` | — | — | × | — | — | — | — | — | — | — | — |
| `FACTORIAL` | S | S | S | S | S | S | S | S | S | S | S |
| `FAMILY` | — | × | — | — | — | — | — | — | — | — | — |
| `FARMFINGERPRINT64` | S | S | S | S | S | S | S | S | S | S | S |
| `FARM_FINGERPRINT` | S | S | S | S | S | S | S | S | S | S | S |
| `FAVG` | × | — | — | — | — | — | — | — | — | — | — |
| `FDIV` | × | — | — | — | — | — | — | — | — | — | — |
| `FEATURES` | — | — | — | — | — | — | — | — | — | × | × |
| `FEATURES_AT_TIME` | S | S | S | S | S | S | S | S | S | S | S |
| `FILEGROUPPROPERTY` | — | — | — | — | — | E | — | — | — | — | — |
| `FILEGROUP_ID` | — | — | — | — | — | E | — | — | — | — | — |
| `FILEGROUP_NAME` | — | — | — | — | — | E | — | — | — | — | — |
| `FILEPROPERTY` | — | — | — | — | — | E | — | — | — | — | — |
| `FILEPROPERTYEX` | — | — | — | — | — | × | — | — | — | — | — |
| `FILE_ID` | — | — | — | — | — | E | — | — | — | — | — |
| `FILE_IDEX` | — | — | — | — | — | E | — | — | — | — | — |
| `FILE_NAME` | — | — | — | — | — | E | — | — | — | — | — |
| `FILL` | × | — | — | — | — | — | — | — | — | — | — |
| `FILTER` | S | S | S | S | S | S | S | S | S | S | S |
| `FIND_IN_SET` | — | — | — | — | E | — | — | E | — | — | — |
| `FIRST` | S | S | S | S | S | S | S | S | S | S | S |
| `FIRST_VALUE` | S | S | S | S | S | S | S | S | S | S | S |
| `FLATTEN` | S | S | S | S | S | S | S | S | S | S | S |
| `FLOAT` | — | — | — | — | S | — | — | S | — | — | — |
| `FLOAT64` | S | S | S | S | S | S | S | S | S | S | S |
| `FLOOR` | S | S | S | S | S | S | S | S | S | S | S |
| `FL_GET_CONTENT_TYPE` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_GET_ETAG` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_GET_FILE_TYPE` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_GET_LAST_MODIFIED` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_GET_RELATIVE_PATH` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_GET_SCOPED_FILE_URL` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_GET_SIZE` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_GET_STAGE` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_GET_STAGE_FILE_URL` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_IS_AUDIO` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_IS_COMPRESSED` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_IS_DOCUMENT` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_IS_IMAGE` | — | — | × | — | — | — | — | — | — | — | — |
| `FL_IS_VIDEO` | — | — | × | — | — | — | — | — | — | — | — |
| `FMOD` | × | — | — | — | — | — | — | — | — | — | — |
| `FNV_HASH` | — | — | — | — | — | — | — | — | E | — | — |
| `FORALL` | — | — | — | — | × | — | — | × | — | — | — |
| `FORCE_CHECKPOINT` | × | — | — | — | — | — | — | — | — | — | — |
| `FORECAST` | — | — | — | S | — | — | — | — | — | — | — |
| `FORMAT` | S | S | S | S | S | S | S | S | S | S | S |
| `FORMATMESSAGE` | — | — | — | — | — | E | — | — | — | — | — |
| `FORMAT_BYTES` | × | — | — | — | — | — | — | — | — | — | — |
| `FORMAT_DATE` | — | — | — | S | — | — | — | — | — | — | — |
| `FORMAT_DATETIME` | — | — | — | S | — | — | — | — | — | × | × |
| `FORMAT_NUMBER` | — | — | — | — | E | — | — | E | — | E | E |
| `FORMAT_STRING` | — | — | — | — | S | — | — | S | — | — | — |
| `FORMAT_STRING_TEMPLATE` | — | — | × | — | — | — | — | — | — | — | — |
| `FORMAT_TIME` | — | — | — | S | — | — | — | — | — | — | — |
| `FORMAT_TIMESTAMP` | — | — | — | S | — | — | — | — | — | — | — |
| `FORMAT_TYPE` | — | × | — | — | — | — | — | — | — | — | — |
| `FROM_AVRO` | — | — | — | — | — | — | — | × | — | — | — |
| `FROM_BASE` | S | S | S | S | S | S | S | S | S | S | S |
| `FROM_BASE32` | S | S | S | S | S | S | S | S | S | S | S |
| `FROM_BASE64` | S | S | S | S | S | S | S | S | S | S | S |
| `FROM_BASE64URL` | — | — | — | — | — | — | — | — | — | × | × |
| `FROM_BIG_ENDIAN_32` | — | — | — | — | — | — | — | — | — | × | × |
| `FROM_BIG_ENDIAN_64` | — | — | — | — | — | — | — | — | — | × | × |
| `FROM_BINARY` | × | — | — | — | — | — | — | — | — | — | — |
| `FROM_CSV` | — | — | — | — | E | — | — | E | — | — | — |
| `FROM_ENCODED_POLYLINE` | — | — | — | — | — | — | — | — | — | × | × |
| `FROM_GEOJSON_GEOMETRY` | — | — | — | — | — | — | — | — | — | — | × |
| `FROM_HEX` | S | — | — | S | — | — | — | — | × | S | S |
| `FROM_IEEE754_32` | — | — | — | — | — | — | — | — | — | × | × |
| `FROM_IEEE754_64` | — | — | — | — | — | — | — | — | — | × | × |
| `FROM_ISO8601_DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `FROM_ISO8601_TIMESTAMP` | S | S | S | S | S | S | S | S | S | S | S |
| `FROM_ISO8601_TIMESTAMP_NANOS` | S | S | S | S | S | S | S | S | S | S | S |
| `FROM_JSON` | S | S | S | S | S | S | S | S | S | S | S |
| `FROM_PROTOBUF` | — | — | — | — | — | — | — | × | — | — | — |
| `FROM_UNIXTIME` | — | — | — | — | S | — | — | S | — | S | S |
| `FROM_UNIXTIME_NANOS` | — | — | — | — | — | — | — | — | — | × | × |
| `FROM_UTC_TIMESTAMP` | — | — | — | — | S | — | — | S | — | — | — |
| `FROM_UTF8` | — | — | — | — | — | — | — | — | — | S | S |
| `FROM_VARBYTE` | — | — | — | — | — | — | — | — | × | — | — |
| `FROM_XML` | — | — | — | — | — | — | — | E | — | — | — |
| `FSUM` | × | — | — | — | — | — | — | — | — | — | — |
| `FULLTEXTCATALOGPROPERTY` | — | — | — | — | — | × | — | — | — | — | — |
| `FULLTEXTSERVICEPROPERTY` | — | — | — | — | — | × | × | — | — | — | — |
| `FUNC_SHA1` | — | — | — | — | — | — | — | — | × | — | — |
| `GAMMA` | × | × | — | — | — | — | — | — | — | — | — |
| `GAP_FILL` | S | S | S | S | S | S | S | S | S | S | S |
| `GCD` | × | × | — | — | — | — | — | — | — | — | — |
| `GENERATE` | — | — | — | S | — | — | — | — | — | — | — |
| `GENERATE_ARRAY` | — | — | — | S | — | — | — | — | — | — | — |
| `GENERATE_BOOL` | S | S | S | S | S | S | S | S | S | S | S |
| `GENERATE_COLUMN_DESCRIPTION` | — | — | × | — | — | — | — | — | — | — | — |
| `GENERATE_DATE_ARRAY` | S | S | S | S | S | S | S | S | S | S | S |
| `GENERATE_DOUBLE` | S | S | S | S | S | S | S | S | S | S | S |
| `GENERATE_EMBEDDING` | S | S | S | S | S | S | S | S | S | S | S |
| `GENERATE_INT` | S | S | S | S | S | S | S | S | S | S | S |
| `GENERATE_POSTGRES_ACCESS_TOKEN_FOR_USER` | — | — | × | — | — | — | — | — | — | — | — |
| `GENERATE_RANGE_ARRAY` | — | — | — | E | — | — | — | — | — | — | — |
| `GENERATE_SERIES` | S | S | S | S | S | S | S | S | S | S | S |
| `GENERATE_SUBSCRIPTS` | × | × | — | — | — | — | — | — | — | — | — |
| `GENERATE_TABLE` | S | S | S | S | S | S | S | S | S | S | S |
| `GENERATE_TEXT` | S | S | S | S | S | S | S | S | S | S | S |
| `GENERATE_TEXT_EMBEDDING` | — | — | — | S | — | — | — | — | — | — | — |
| `GENERATE_TIMESTAMP_ARRAY` | S | S | S | S | S | S | S | S | S | S | S |
| `GENERATE_UUID` | S | S | S | S | S | S | S | S | S | S | S |
| `GENERATOR` | S | S | S | S | S | S | S | S | S | S | S |
| `GEN_RANDOM_UUID` | S | S | S | S | S | S | S | S | S | S | S |
| `GEOHASH` | — | — | × | — | — | — | — | — | — | — | — |
| `GEOMETRIC_MEAN` | × | — | — | — | — | — | — | — | — | × | × |
| `GEOMETRY_COLLECT_AGG` | — | — | — | — | — | — | — | — | — | × | × |
| `GEOMETRY_FROM_HADOOP_SHAPE` | — | — | — | — | — | — | — | — | — | × | × |
| `GEOMETRY_INVALID_REASON` | — | — | — | — | — | — | — | — | — | × | × |
| `GEOMETRY_NEAREST_POINTS` | — | — | — | — | — | — | — | — | — | × | × |
| `GEOMETRY_TO_BING_TILES` | — | — | — | — | — | — | — | — | — | × | × |
| `GEOMETRY_UNION` | — | — | — | — | — | — | — | — | — | × | × |
| `GEOMETRY_UNION_AGG` | — | — | — | — | — | — | — | — | — | × | × |
| `GET` | — | — | S | — | E | — | — | E | — | — | — |
| `GETANSINULL` | — | — | — | — | — | × | — | — | — | — | — |
| `GETBIT` | S | S | S | S | S | S | S | S | S | S | S |
| `GETDATE` | — | — | S | — | — | S | S | S | S | — | — |
| `GETENV` | × | — | — | — | — | — | — | — | — | — | — |
| `GETUTCDATE` | — | — | — | — | — | × | × | — | — | — | — |
| `GETVARIABLE` | × | — | × | — | — | — | — | — | — | — | — |
| `GET_ABSOLUTE_PATH` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_ANACONDA_PACKAGES_REPODATA` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_ARRAY_LENGTH` | — | — | — | — | — | — | — | — | E | — | — |
| `GET_BIT` | S | S | S | S | S | S | S | S | — | S | S |
| `GET_BLOCK_SIZE` | × | — | — | — | — | — | — | — | — | — | — |
| `GET_BYTE` | — | × | — | — | — | — | — | — | — | — | — |
| `GET_CONDITION_QUERY_UUID` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_CONTACTS` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_CURRENT_TIME` | B | — | — | — | — | — | — | — | — | — | — |
| `GET_CURRENT_TIMESTAMP` | × | — | — | — | — | — | — | — | — | — | — |
| `GET_CURRENT_TS_CONFIG` | — | × | — | — | — | — | — | — | — | — | — |
| `GET_DDL` | — | — | E | — | — | — | — | — | — | — | — |
| `GET_EXTRACT` | S | S | S | S | S | S | S | S | S | S | S |
| `GET_FILESTREAM_TRANSACTION_CONTEXT` | — | — | — | — | — | × | — | — | — | — | — |
| `GET_IGNORE_CASE` | S | S | S | S | S | S | S | S | S | S | S |
| `GET_JOB_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_JSON_OBJECT` | — | — | — | — | S | — | — | S | — | — | — |
| `GET_MOUNTED_ROLE` | — | — | — | — | — | — | — | — | × | — | — |
| `GET_NUMBER_ATTRIBUTES` | — | — | — | — | — | — | — | — | × | — | — |
| `GET_OBJECT_REFERENCES` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_PATH` | — | — | S | — | — | — | — | — | — | — | — |
| `GET_PRESIGNED_URL` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_QUERY_OPERATOR_STATS` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_RELATIVE_PATH` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_STAGE_LOCATION` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_TABLE_VERSIONS` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_TABLE_VERSION_REFS` | — | — | × | — | — | — | — | — | — | — | — |
| `GET_TYPE` | × | — | — | — | — | — | — | — | — | — | — |
| `GIN_CLEAN_PENDING_LIST` | — | × | — | — | — | — | — | — | — | — | — |
| `GLOB` | × | S | S | S | S | S | S | S | S | S | S |
| `GRADE_UP` | × | — | — | — | — | — | — | — | — | — | — |
| `GRAPH_ID_FROM_EDGE_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `GRAPH_ID_FROM_NODE_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `GREATEST` | S | S | S | S | S | S | S | S | S | S | S |
| `GREATEST_COMMON_DIVISOR` | × | — | — | — | — | — | — | — | — | — | — |
| `GREATEST_IGNORE_NULLS` | — | — | S | — | — | — | — | — | — | — | — |
| `GREAT_CIRCLE_DISTANCE` | — | — | — | — | — | — | — | — | — | × | × |
| `GROUPING` | S | S | S | S | S | S | S | S | S | S | S |
| `GROUPING_ID` | S | S | S | S | S | S | S | S | S | S | S |
| `GROUP_CONCAT` | S | S | S | S | S | S | S | S | S | S | S |
| `H3_BOUNDARYASGEOJSON` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_BOUNDARYASWKB` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_BOUNDARYASWKT` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_CELL_TO_BOUNDARY` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_CELL_TO_CHILDREN` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_CELL_TO_CHILDREN_STRING` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_CELL_TO_PARENT` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_CELL_TO_POINT` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_CENTERASGEOJSON` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_CENTERASWKB` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_CENTERASWKT` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_COMPACT` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_COMPACT_CELLS` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_COMPACT_CELLS_STRINGS` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_COVERAGE` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_COVERAGE_STRINGS` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_COVERASH3` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_COVERASH3STRING` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_DISTANCE` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_GET_RESOLUTION` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_GRID_DISK` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_GRID_DISTANCE` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_GRID_PATH` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_H3TOSTRING` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_HEXRING` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_INT_TO_STRING` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_ISCHILDOF` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_ISPENTAGON` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_ISVALID` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_IS_PENTAGON` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_IS_VALID_CELL` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_KRING` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_KRINGDISTANCES` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_LATLNG_TO_CELL` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_LATLNG_TO_CELL_STRING` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_LONGLATASH3` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_LONGLATASH3STRING` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_MAXCHILD` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_MINCHILD` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_POINTASH3` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_POINTASH3STRING` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_POINT_TO_CELL` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_POINT_TO_CELL_STRING` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_POLYFILLASH3` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_POLYFILLASH3STRING` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_POLYGON_TO_CELLS` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_POLYGON_TO_CELLS_STRINGS` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_RESOLUTION` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_STRINGTOH3` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_STRING_TO_INT` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_TESSELLATEASWKB` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_TOCHILDREN` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_TOPARENT` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_TRY_COVERAGE` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_TRY_COVERAGE_STRINGS` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_TRY_COVERASH3` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_TRY_COVERASH3STRING` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_TRY_DISTANCE` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_TRY_GRID_DISTANCE` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_TRY_GRID_PATH` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_TRY_POLYFILLASH3` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_TRY_POLYFILLASH3STRING` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_TRY_POLYGON_TO_CELLS` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_TRY_POLYGON_TO_CELLS_STRINGS` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_TRY_TESSELLATEASWKB` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_TRY_VALIDATE` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_UNCOMPACT` | — | — | — | — | — | — | — | × | — | — | — |
| `H3_UNCOMPACT_CELLS` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_UNCOMPACT_CELLS_STRINGS` | — | — | × | — | — | — | — | — | — | — | — |
| `H3_VALIDATE` | — | — | — | — | — | — | — | × | — | — | — |
| `HAMMING` | × | — | — | — | — | — | — | — | — | — | — |
| `HAMMING_DISTANCE` | — | — | — | — | — | — | — | — | — | × | × |
| `HASH` | × | — | E | — | × | — | — | × | — | — | — |
| `HASHBYTES` | — | — | — | — | — | S | S | — | — | — | — |
| `HASH_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `HASH_COUNTS` | — | — | — | — | — | — | — | — | — | × | × |
| `HAS_ANY_COLUMN_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAS_ASSUMEROLE_PRIVILEGE` | — | — | — | — | — | — | — | — | × | — | — |
| `HAS_COLUMN_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAS_DATABASE_PRIVILEGE` | — | × | — | — | — | — | — | — | × | — | — |
| `HAS_DBACCESS` | — | — | — | — | — | × | — | — | — | — | — |
| `HAS_FOREIGN_DATA_WRAPPER_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAS_FUNCTION_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAS_LANGUAGE_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAS_LARGEOBJECT_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAS_PARAMETER_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAS_PERMS_BY_NAME` | — | — | — | — | — | E | — | — | — | — | — |
| `HAS_SCHEMA_PRIVILEGE` | — | × | — | — | — | — | — | — | × | — | — |
| `HAS_SEQUENCE_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAS_SERVER_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAS_TABLESPACE_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAS_TABLE_PRIVILEGE` | — | × | — | — | — | — | — | — | × | — | — |
| `HAS_TYPE_PRIVILEGE` | — | × | — | — | — | — | — | — | — | — | — |
| `HAVERSINE` | — | — | × | — | — | — | — | — | — | — | — |
| `HEIGHT` | — | × | — | — | — | — | — | — | — | — | — |
| `HEX` | S | S | S | S | S | S | S | S | S | S | S |
| `HEX_DECODE_BINARY` | — | — | S | — | — | — | — | — | — | — | — |
| `HEX_DECODE_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `HEX_ENCODE` | — | — | S | — | — | — | — | — | — | — | — |
| `HISTOGRAM` | × | — | — | — | — | — | — | — | — | × | × |
| `HISTOGRAM_EXACT` | × | — | — | — | — | — | — | — | — | — | — |
| `HISTOGRAM_NUMERIC` | — | — | — | — | E | — | — | E | — | — | — |
| `HISTOGRAM_VALUES` | × | — | — | — | — | — | — | — | — | — | — |
| `HLL` | S | S | S | S | S | S | S | S | S | S | S |
| `HLL_ACCUMULATE` | — | — | × | — | — | — | — | — | — | — | — |
| `HLL_CARDINALITY` | — | — | — | — | — | — | — | — | × | — | — |
| `HLL_COMBINE` | — | — | × | — | — | — | — | — | × | — | — |
| `HLL_COMBINE_SKETCHES` | — | — | — | — | — | — | — | — | × | — | — |
| `HLL_COUNT.EXTRACT` | — | — | — | × | — | — | — | — | — | — | — |
| `HLL_COUNT.INIT` | — | — | — | × | — | — | — | — | — | — | — |
| `HLL_COUNT.MERGE` | — | — | — | × | — | — | — | — | — | — | — |
| `HLL_COUNT.MERGE_PARTIAL` | — | — | — | × | — | — | — | — | — | — | — |
| `HLL_CREATE_SKETCH` | — | — | — | — | — | — | — | — | × | — | — |
| `HLL_ESTIMATE` | — | — | E | — | — | — | — | — | — | — | — |
| `HLL_EXPORT` | — | — | × | — | — | — | — | — | — | — | — |
| `HLL_IMPORT` | — | — | × | — | — | — | — | — | — | — | — |
| `HLL_SKETCH_AGG` | — | — | — | — | E | — | — | E | — | — | — |
| `HLL_SKETCH_ESTIMATE` | — | — | — | — | E | — | — | E | — | — | — |
| `HLL_UNION` | — | — | — | — | E | — | — | E | — | — | — |
| `HLL_UNION_AGG` | — | — | — | — | E | — | — | E | — | — | — |
| `HMAC` | — | — | — | — | — | — | — | × | — | — | — |
| `HMAC_MD5` | — | — | — | — | — | — | — | — | — | × | × |
| `HMAC_SHA1` | — | — | — | — | — | — | — | — | — | × | × |
| `HMAC_SHA256` | — | — | — | — | — | — | — | — | — | × | × |
| `HMAC_SHA512` | — | — | — | — | — | — | — | — | — | × | × |
| `HOST` | S | S | S | S | S | S | S | S | S | S | S |
| `HOSTMASK` | — | × | — | — | — | — | — | — | — | — | — |
| `HOST_ID` | — | — | — | — | — | E | — | — | — | — | — |
| `HOST_NAME` | — | — | — | — | — | E | — | — | — | — | — |
| `HOUR` | S | S | S | S | S | S | S | S | S | S | S |
| `HTTP_REQUEST` | — | — | — | — | — | — | — | × | — | — | — |
| `HUMAN_READABLE_SECONDS` | — | — | — | — | — | — | — | — | — | E | × |
| `HYPOT` | — | — | — | — | E | — | — | E | — | — | — |
| `ICEBERG_TABLE_FILES` | — | — | × | — | — | — | — | — | — | — | — |
| `ICEBERG_TABLE_FILE_REGISTRATION_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `ICEBERG_TABLE_SNAPSHOT_REFRESH_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `ICU_SORT_KEY` | × | — | — | — | — | — | — | — | — | — | — |
| `ICU_UNICODE_VERSION` | — | × | — | — | — | — | — | — | — | — | — |
| `IDENTIFIER` | — | — | S | — | — | — | — | — | — | — | — |
| `IDENT_CURRENT` | — | — | — | — | — | E | — | — | — | — | — |
| `IDENT_INCR` | — | — | — | — | — | E | — | — | — | — | — |
| `IDENT_SEED` | — | — | — | — | — | E | — | — | — | — | — |
| `IEEE_DIVIDE` | — | — | — | × | — | — | — | — | — | — | — |
| `IF` | S | S | S | S | S | S | S | S | S | S | S |
| `IFF` | — | — | S | — | — | — | — | S | — | — | — |
| `IFNULL` | S | S | S | S | S | S | S | S | S | S | S |
| `IIF` | S | S | S | S | S | S | S | S | S | S | S |
| `ILIKE` | — | × | S | — | S | — | — | S | — | — | — |
| `ILIKE_ESCAPE` | × | — | — | — | — | — | — | — | — | — | — |
| `INDEX` | — | — | — | — | — | — | — | — | — | × | × |
| `INDEXKEY_PROPERTY` | — | — | — | — | — | × | × | — | — | — | — |
| `INDEXPROPERTY` | — | — | — | — | — | E | × | — | — | — | — |
| `INDEX_COL` | — | — | — | — | — | E | × | — | — | — | — |
| `INET_CLIENT_ADDR` | — | × | — | — | — | — | — | — | — | — | — |
| `INET_CLIENT_PORT` | — | × | — | — | — | — | — | — | — | — | — |
| `INET_MERGE` | — | × | — | — | — | — | — | — | — | — | — |
| `INET_SAME_FAMILY` | — | × | — | — | — | — | — | — | — | — | — |
| `INET_SERVER_ADDR` | — | × | — | — | — | — | — | — | — | — | — |
| `INET_SERVER_PORT` | — | × | — | — | — | — | — | — | — | — | — |
| `INFER_SCHEMA` | — | — | × | — | — | — | — | — | — | — | — |
| `INFINITY` | — | — | — | — | — | — | — | — | — | × | × |
| `INITCAP` | S | S | S | S | S | S | S | S | S | S | S |
| `INLINE` | S | S | S | S | S | S | S | S | S | S | S |
| `INLINE_OUTER` | — | — | — | — | E | — | — | E | — | — | — |
| `INPUT_FILE_BLOCK_LENGTH` | — | — | — | — | E | — | — | × | — | — | — |
| `INPUT_FILE_BLOCK_START` | — | — | — | — | E | — | — | × | — | — | — |
| `INPUT_FILE_NAME` | — | — | — | — | E | — | — | × | — | — | — |
| `INSERT` | S | S | S | S | S | S | S | S | S | S | S |
| `INSTR` | S | S | S | S | S | S | S | S | S | S | S |
| `INT` | — | — | — | — | S | — | — | S | — | — | — |
| `INT64` | S | S | S | S | S | S | S | S | S | S | S |
| `INTEGRATION` | — | — | × | — | — | — | — | — | — | — | — |
| `INTERSECTION_CARDINALITY` | — | — | — | — | — | — | — | — | — | × | × |
| `INTERVAL_CMP` | — | — | — | — | — | — | — | — | × | — | — |
| `INVERSE_BETA_CDF` | — | — | — | — | — | — | — | — | — | × | × |
| `INVERSE_NORMAL_CDF` | — | — | — | — | — | — | — | — | — | × | × |
| `INVOKER_PRINCIPAL` | — | — | — | — | — | — | — | — | — | — | E |
| `INVOKER_ROLE` | — | — | × | — | — | — | — | — | — | — | — |
| `INVOKER_SHARE` | — | — | × | — | — | — | — | — | — | — | — |
| `IN_SEARCH_PATH` | × | — | — | — | — | — | — | — | — | — | — |
| `IPADDRESS_TRUNC` | — | — | × | — | — | — | — | — | — | — | — |
| `IP_AS_BINARY` | — | — | — | — | — | — | — | × | — | — | — |
| `IP_AS_STRING` | — | — | — | — | — | — | — | × | — | — | — |
| `IP_CIDR` | — | — | — | — | — | — | — | × | — | — | — |
| `IP_CIDR_CONTAINS` | — | — | — | — | — | — | — | × | — | — | — |
| `IP_HOST` | — | — | — | — | — | — | — | × | — | — | — |
| `IP_NETWORK` | — | — | — | — | — | — | — | × | — | — | — |
| `IP_NETWORK_FIRST` | — | — | — | — | — | — | — | × | — | — | — |
| `IP_NETWORK_LAST` | — | — | — | — | — | — | — | × | — | — | — |
| `IP_PREFIX_LENGTH` | — | — | — | — | — | — | — | × | — | — | — |
| `IP_VERSION` | — | — | — | — | — | — | — | × | — | — | — |
| `ISCLOSED` | — | × | — | — | — | — | — | — | — | — | — |
| `ISDATE` | — | — | — | — | — | E | × | — | — | — | — |
| `ISEARCH` | — | — | — | — | — | — | — | × | — | — | — |
| `ISEMPTY` | — | × | — | — | — | — | — | — | — | — | — |
| `ISFINITE` | × | × | — | — | — | — | — | — | — | — | — |
| `ISINF` | S | S | S | S | S | S | S | S | S | S | S |
| `ISJSON` | — | — | — | — | — | E | E | — | — | — | — |
| `ISNAN` | S | S | S | S | S | S | S | S | S | S | S |
| `ISNOTNULL` | — | — | — | — | E | — | — | E | — | — | — |
| `ISNULL` | — | — | — | — | E | S | S | E | — | — | — |
| `ISNUMERIC` | — | — | — | — | — | E | E | — | — | — | — |
| `ISODOW` | S | S | S | S | S | S | S | S | S | S | S |
| `ISOPEN` | — | × | — | — | — | — | — | — | — | — | — |
| `ISOYEAR` | × | — | — | — | — | — | — | — | — | — | — |
| `IS_ACCOUNT_GROUP_MEMBER` | — | — | — | — | — | — | — | × | — | — | — |
| `IS_ACYCLIC` | — | — | — | × | — | — | — | — | — | — | — |
| `IS_APPLICATION_ROLE_IN_SESSION` | — | — | × | — | — | — | — | — | — | — | — |
| `IS_ARRAY` | S | S | B | S | S | S | S | S | S | S | S |
| `IS_ASCII` | S | S | S | S | S | S | S | S | S | S | S |
| `IS_BIGINT` | — | — | — | — | — | — | — | — | × | — | — |
| `IS_BINARY` | — | — | × | — | — | — | — | — | — | — | — |
| `IS_BOOLEAN` | — | — | E | — | — | — | — | — | E | — | — |
| `IS_CHAR` | — | — | — | — | — | — | — | — | × | — | — |
| `IS_DATABASE_ROLE_IN_SESSION` | — | — | E | — | — | — | — | — | — | — | — |
| `IS_DATE_VALUE` | — | — | E | — | — | — | — | — | — | — | — |
| `IS_DECIMAL` | — | — | E | — | — | — | — | — | E | — | — |
| `IS_DOUBLE` | — | — | E | — | — | — | — | — | — | — | — |
| `IS_FINITE` | — | — | — | — | — | — | — | — | — | × | × |
| `IS_FLOAT` | — | — | — | — | — | — | — | — | E | — | — |
| `IS_GRANTED_TO_INVOKER_ROLE` | — | — | × | — | — | — | — | — | — | — | — |
| `IS_HISTOGRAM_OTHER_BIN` | × | — | — | — | — | — | — | — | — | — | — |
| `IS_INF` | S | S | S | S | S | S | S | S | S | S | S |
| `IS_INFINITE` | — | — | — | — | — | — | — | — | — | × | × |
| `IS_INSTANCE_ROLE_IN_SESSION` | — | — | × | — | — | — | — | — | — | — | — |
| `IS_INTEGER` | — | — | E | — | — | — | — | — | E | — | — |
| `IS_JSON_SCALAR` | — | — | — | — | — | — | — | — | — | E | E |
| `IS_MEMBER` | — | — | — | — | — | E | — | × | — | — | — |
| `IS_NAN` | S | S | S | S | S | S | S | S | S | S | S |
| `IS_NULL_VALUE` | S | S | S | S | S | S | S | S | S | S | S |
| `IS_OBJECT` | — | — | E | — | — | — | — | — | E | — | — |
| `IS_OBJECTSIGNED` | — | — | — | — | — | × | — | — | — | — | — |
| `IS_ORGANIZATION_USER` | — | — | × | — | — | — | — | — | — | — | — |
| `IS_ORGANIZATION_USER_GROUP` | — | — | × | — | — | — | — | — | — | — | — |
| `IS_ORGANIZATION_USER_GROUP_IN_SESSION` | — | — | × | — | — | — | — | — | — | — | — |
| `IS_ROLEMEMBER` | — | — | — | — | — | E | — | — | — | — | — |
| `IS_ROLE_IN_SESSION` | — | — | E | — | — | — | — | — | — | — | — |
| `IS_SCALAR` | — | — | — | — | — | — | — | — | × | — | — |
| `IS_SIMPLE` | — | — | — | × | — | — | — | — | — | — | — |
| `IS_SMALLINT` | — | — | — | — | — | — | — | — | × | — | — |
| `IS_SRVROLEMEMBER` | — | — | — | — | — | E | — | — | — | — | — |
| `IS_TIME` | — | — | × | — | — | — | — | — | — | — | — |
| `IS_TIMESTAMP_NTZ` | — | — | E | — | — | — | — | — | — | — | — |
| `IS_TRAIL` | — | — | — | × | — | — | — | — | — | — | — |
| `IS_VALID_JSON` | — | — | — | — | — | — | — | — | E | — | — |
| `IS_VALID_JSON_ARRAY` | — | — | — | — | — | — | — | — | E | — | — |
| `IS_VALID_UTF8` | — | — | — | — | — | — | — | × | — | — | — |
| `IS_VARCHAR` | — | — | — | — | — | — | — | — | E | — | — |
| `IS_VARIANT_NULL` | — | — | — | — | — | — | — | E | — | — | — |
| `JACCARD` | × | — | — | — | — | — | — | — | — | — | — |
| `JACCARD_INDEX` | — | — | — | — | — | — | — | — | — | × | × |
| `JAROWINKLER_SIMILARITY` | S | S | S | S | S | S | S | S | S | S | S |
| `JARO_SIMILARITY` | × | — | — | — | — | — | — | — | — | — | — |
| `JARO_WINKLER_DISTANCE` | — | — | — | — | — | × | × | — | — | — | — |
| `JARO_WINKLER_SIMILARITY` | S | — | — | — | — | × | × | × | — | — | — |
| `JAVA_METHOD` | — | — | — | — | E | — | — | E | — | — | — |
| `JSON` | S | × | — | — | — | — | — | — | — | × | — |
| `JSONB_AGG` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_AGG_STRICT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_ARRAY_ELEMENTS` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_ARRAY_ELEMENTS_TEXT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_ARRAY_LENGTH` | — | E | — | — | — | — | — | — | — | — | — |
| `JSONB_BUILD_ARRAY` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_BUILD_OBJECT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_CONTAINS` | S | S | S | S | S | S | S | S | S | S | S |
| `JSONB_EACH` | — | E | — | — | — | — | — | — | — | — | — |
| `JSONB_EACH_TEXT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_EXISTS` | S | S | S | S | S | S | S | S | S | S | S |
| `JSONB_EXTRACT` | S | S | S | S | S | S | S | S | S | S | S |
| `JSONB_EXTRACT_PATH` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_EXTRACT_PATH_TEXT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_EXTRACT_SCALAR` | S | S | S | S | S | S | S | S | S | S | S |
| `JSONB_INSERT` | — | E | — | — | — | — | — | — | — | — | — |
| `JSONB_OBJECT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_OBJECT_AGG` | — | S | — | — | — | — | — | — | S | — | — |
| `JSONB_OBJECT_AGG_STRICT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_OBJECT_AGG_UNIQUE` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_OBJECT_AGG_UNIQUE_STRICT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_OBJECT_KEYS` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_PATH_EXISTS` | — | E | — | — | — | — | — | — | — | — | — |
| `JSONB_PATH_EXISTS_TZ` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_PATH_MATCH` | — | E | — | — | — | — | — | — | — | — | — |
| `JSONB_PATH_MATCH_TZ` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_PATH_QUERY` | — | E | — | — | — | — | — | — | — | — | — |
| `JSONB_PATH_QUERY_ARRAY` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_PATH_QUERY_ARRAY_TZ` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_PATH_QUERY_FIRST` | — | E | — | — | — | — | — | — | — | — | — |
| `JSONB_PATH_QUERY_FIRST_TZ` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_PATH_QUERY_TZ` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_POPULATE_RECORD` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_POPULATE_RECORDSET` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_POPULATE_RECORD_VALID` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_PRETTY` | — | E | — | — | — | — | — | — | — | — | — |
| `JSONB_SET` | — | E | — | — | — | — | — | — | — | — | — |
| `JSONB_SET_LAX` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_STRIP_NULLS` | — | E | — | — | — | — | — | — | — | — | — |
| `JSONB_TO_RECORD` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_TO_RECORDSET` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_TO_TSVECTOR` | — | × | — | — | — | — | — | — | — | — | — |
| `JSONB_TYPEOF` | — | E | — | — | — | — | — | — | — | — | — |
| `JSON_AGG` | — | S | — | — | — | — | — | — | S | — | — |
| `JSON_AGG_STRICT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_ARRAY` | S | × | — | S | — | × | × | — | — | × | — |
| `JSON_ARRAYAGG` | — | × | — | — | — | S | S | — | — | — | — |
| `JSON_ARRAY_APPEND` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_ARRAY_CONTAINS` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_ARRAY_ELEMENTS` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_ARRAY_ELEMENTS_TEXT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_ARRAY_GET` | — | — | — | — | — | — | — | — | — | × | × |
| `JSON_ARRAY_INSERT` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_ARRAY_LENGTH` | E | × | — | — | E | — | — | E | E | E | E |
| `JSON_BUILD_ARRAY` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_BUILD_OBJECT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_CONTAINS` | E | — | — | — | — | × | — | — | — | — | — |
| `JSON_EACH` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_EACH_TEXT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_EXISTS` | — | × | — | — | — | — | — | — | — | × | — |
| `JSON_EXTRACT` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_EXTRACT_ARRAY` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_EXTRACT_ARRAY_ELEMENT_TEXT` | — | — | — | — | — | — | — | — | E | — | — |
| `JSON_EXTRACT_PATH` | S | S | — | — | — | — | — | — | S | — | — |
| `JSON_EXTRACT_PATH_TEXT` | S | S | S | S | S | S | S | S | B | S | S |
| `JSON_EXTRACT_SCALAR` | B | S | S | S | S | S | S | S | B | S | S |
| `JSON_EXTRACT_STRING` | B | — | — | — | — | — | — | — | — | — | — |
| `JSON_EXTRACT_STRING_ARRAY` | — | — | — | S | — | — | — | — | — | — | — |
| `JSON_FLATTEN` | — | — | — | × | — | — | — | — | — | — | — |
| `JSON_FORMAT` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_GROUP_ARRAY` | E | — | — | — | — | — | — | — | — | — | — |
| `JSON_GROUP_OBJECT` | E | — | — | — | — | — | — | — | — | — | — |
| `JSON_GROUP_STRUCTURE` | E | — | — | — | — | — | — | — | — | — | — |
| `JSON_KEYS` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_MODIFY` | — | — | — | — | — | E | E | — | — | — | — |
| `JSON_OBJECT` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_OBJECTAGG` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_OBJECT_AGG` | — | S | — | — | — | — | — | — | S | — | — |
| `JSON_OBJECT_AGG_STRICT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_OBJECT_AGG_UNIQUE` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_OBJECT_AGG_UNIQUE_STRICT` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_OBJECT_KEYS` | — | × | — | — | S | — | — | S | — | — | — |
| `JSON_PARSE` | S | S | S | S | S | S | S | B | B | S | S |
| `JSON_PATH_EXISTS` | — | — | — | — | — | E | E | — | — | — | — |
| `JSON_POPULATE_RECORD` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_POPULATE_RECORDSET` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_QUERY` | — | × | — | S | — | S | S | — | — | S | S |
| `JSON_QUERY_ARRAY` | — | — | — | S | — | — | — | — | — | — | — |
| `JSON_REMOVE` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_SCALAR` | — | × | — | — | — | — | — | — | — | × | × |
| `JSON_SERIALIZE` | — | × | — | — | — | — | — | — | E | × | — |
| `JSON_SERIALIZE_TO_VARBYTE` | — | — | — | — | — | — | — | — | E | — | — |
| `JSON_SET` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_SIZE` | — | — | — | — | — | — | — | — | E | E | E |
| `JSON_STRIP_NULLS` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_STRUCTURE` | E | — | — | — | — | — | — | — | — | — | — |
| `JSON_TABLE` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_TO_RECORD` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_TO_RECORDSET` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_TO_TSVECTOR` | — | × | — | — | — | — | — | — | — | — | — |
| `JSON_TRANSFORM` | E | — | — | — | — | — | — | — | — | — | — |
| `JSON_TUPLE` | — | — | — | — | E | — | — | E | — | — | — |
| `JSON_TYPE` | S | S | S | S | S | S | S | S | S | S | S |
| `JSON_TYPEOF` | — | × | — | — | — | — | — | — | E | — | — |
| `JSON_VALID` | E | — | — | — | — | — | — | — | — | — | — |
| `JSON_VALUE` | — | S | — | S | — | S | S | — | S | S | S |
| `JSON_VALUE_ARRAY` | — | — | — | S | — | — | — | — | — | — | — |
| `JULIAN` | × | — | — | — | — | — | — | — | — | — | — |
| `JUSTIFY_DAYS` | S | S | S | S | S | S | S | S | S | S | S |
| `JUSTIFY_HOURS` | S | S | S | S | S | S | S | S | S | S | S |
| `JUSTIFY_INTERVAL` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_ARRAY` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_ARRAY_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_BOOL` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_B_CONTAINS_ALL_TOP_KEYS` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_B_CONTAINS_ANY_TOP_KEYS` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_B_CONTAINS_TOP_KEY` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_B_DELETE_AT_PATH` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_B_OBJECT_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_B_PATH_EXISTS` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_CAST` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_EXISTS` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_KEYS_AT_DEPTH` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_OBJECT` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_OBJECT_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_TABLE` | S | S | S | S | S | S | S | S | S | S | S |
| `J_S_O_N_VALUE_ARRAY` | S | S | S | S | S | S | S | S | S | S | S |
| `KEYS.ADD_KEY_FROM_RAW_BYTES` | — | — | — | × | — | — | — | — | — | — | — |
| `KEYS.KEYSET_CHAIN` | — | — | — | × | — | — | — | — | — | — | — |
| `KEYS.KEYSET_FROM_JSON` | — | — | — | × | — | — | — | — | — | — | — |
| `KEYS.KEYSET_LENGTH` | — | — | — | × | — | — | — | — | — | — | — |
| `KEYS.KEYSET_TO_JSON` | — | — | — | × | — | — | — | — | — | — | — |
| `KEYS.NEW_KEYSET` | — | — | — | × | — | — | — | — | — | — | — |
| `KEYS.NEW_WRAPPED_KEYSET` | — | — | — | × | — | — | — | — | — | — | — |
| `KEYS.REWRAP_KEYSET` | — | — | — | × | — | — | — | — | — | — | — |
| `KEYS.ROTATE_KEYSET` | — | — | — | × | — | — | — | — | — | — | — |
| `KEYS.ROTATE_WRAPPED_KEYSET` | — | — | — | × | — | — | — | — | — | — | — |
| `KEY_GUID` | — | — | — | — | — | × | — | — | — | — | — |
| `KEY_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `KEY_NAME` | — | — | — | — | — | × | — | — | — | — | — |
| `KLL_MERGE_AGG_BIGINT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_MERGE_AGG_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_MERGE_AGG_FLOAT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_QUANTILES.EXTRACT_FLOAT64` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_QUANTILES.EXTRACT_INT64` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_QUANTILES.EXTRACT_POINT_FLOAT64` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_QUANTILES.EXTRACT_POINT_INT64` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_QUANTILES.INIT_FLOAT64` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_QUANTILES.INIT_INT64` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_QUANTILES.MERGE_FLOAT64` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_QUANTILES.MERGE_INT64` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_QUANTILES.MERGE_PARTIAL` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_QUANTILES.MERGE_POINT_FLOAT64` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_QUANTILES.MERGE_POINT_INT64` | — | — | — | × | — | — | — | — | — | — | — |
| `KLL_SKETCH_AGG_BIGINT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_AGG_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_AGG_FLOAT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_GET_N_BIGINT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_GET_N_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_GET_N_FLOAT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_GET_QUANTILE_BIGINT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_GET_QUANTILE_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_GET_QUANTILE_FLOAT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_GET_RANK_BIGINT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_GET_RANK_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_GET_RANK_FLOAT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_MERGE_BIGINT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_MERGE_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_MERGE_FLOAT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_TO_STRING_BIGINT` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_TO_STRING_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `KLL_SKETCH_TO_STRING_FLOAT` | — | — | — | — | — | — | — | × | — | — | — |
| `KURTOSIS` | S | S | S | S | S | S | S | S | S | S | S |
| `KURTOSIS_POP` | × | — | — | — | — | — | — | — | — | — | — |
| `LABELS` | — | — | — | × | — | — | — | — | — | — | — |
| `LAG` | S | S | S | S | S | S | S | S | S | S | S |
| `LAST` | S | S | S | S | S | S | S | S | S | S | S |
| `LASTVAL` | — | × | — | — | — | — | — | — | — | — | — |
| `LAST_DAY` | S | S | S | S | S | S | S | S | S | S | S |
| `LAST_DAY_OF_MONTH` | S | S | S | S | S | S | S | S | S | S | S |
| `LAST_QUERY_ID` | — | — | E | — | — | — | — | — | — | — | — |
| `LAST_SNAPSHOT_VERSION` | — | — | — | — | — | — | — | × | — | — | — |
| `LAST_SUCCESSFUL_SCHEDULED_TIME` | — | — | × | — | — | — | — | — | — | — | — |
| `LAST_TRANSACTION` | — | — | × | — | — | — | — | — | — | — | — |
| `LAST_USER_QUERY_ID` | — | — | — | — | — | — | — | — | × | — | — |
| `LAST_VALUE` | S | S | S | S | S | S | S | S | S | S | S |
| `LAX_BOOL` | S | S | S | S | S | S | S | S | S | S | S |
| `LAX_FLOAT64` | S | S | S | S | S | S | S | S | S | S | S |
| `LAX_INT64` | S | S | S | S | S | S | S | S | S | S | S |
| `LAX_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `LCASE` | S | S | S | S | S | S | S | S | S | S | S |
| `LCM` | × | × | — | — | — | — | — | — | — | — | — |
| `LEAD` | S | S | S | S | S | S | S | S | S | S | S |
| `LEARN_CLASSIFIER` | — | — | — | — | — | — | — | — | — | × | × |
| `LEARN_LIBSVM_CLASSIFIER` | — | — | — | — | — | — | — | — | — | × | × |
| `LEARN_LIBSVM_REGRESSOR` | — | — | — | — | — | — | — | — | — | × | × |
| `LEARN_REGRESSOR` | — | — | — | — | — | — | — | — | — | × | × |
| `LEAST` | S | S | S | S | S | S | S | S | S | S | S |
| `LEAST_COMMON_MULTIPLE` | × | — | — | — | — | — | — | — | — | — | — |
| `LEAST_IGNORE_NULLS` | — | — | S | — | — | — | — | — | — | — | — |
| `LEFT` | S | S | S | S | S | S | S | S | S | S | S |
| `LEFTPAD` | S | S | S | S | S | S | S | S | S | S | S |
| `LEFT_GRAPHEME` | × | — | — | — | — | — | — | — | — | — | — |
| `LEFT_SHIFT` | — | — | — | — | — | E | × | — | — | — | — |
| `LEN` | S | S | S | S | S | S | S | S | S | S | S |
| `LENGTH` | S | S | S | S | S | S | S | S | S | S | S |
| `LENGTH_GRAPHEME` | × | — | — | — | — | — | — | — | — | — | — |
| `LEVENSHTEIN` | S | S | S | S | S | S | S | S | S | S | S |
| `LEVENSHTEIN_DISTANCE` | — | — | — | — | — | — | — | — | — | S | S |
| `LEVENSHTEIN_LESS_EQUAL` | — | S | — | — | — | — | — | — | S | — | — |
| `LGAMMA` | × | × | — | — | — | — | — | — | — | — | — |
| `LIKE` | S | S | S | S | S | S | S | S | S | S | S |
| `LIKE_ESCAPE` | × | — | — | — | — | — | — | — | — | — | — |
| `LINE` | — | × | — | — | — | — | — | — | — | — | — |
| `LINE_INTERPOLATE_POINT` | — | — | — | — | — | — | — | — | — | × | × |
| `LINE_INTERPOLATE_POINTS` | — | — | — | — | — | — | — | — | — | × | × |
| `LINE_LOCATE_POINT` | — | — | — | — | — | — | — | — | — | × | × |
| `LIST` | S | S | S | S | S | S | S | S | S | S | S |
| `LISTAGG` | S | — | S | — | S | — | — | S | S | S | S |
| `LISTING_REFRESH_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `LIST_AGGR` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_AGGREGATE` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_ANY_VALUE` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_APPEND` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_APPLY` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_APPROX_COUNT_DISTINCT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_AVG` | E | — | — | — | — | — | — | — | — | — | — |
| `LIST_BIT_AND` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_BIT_OR` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_BIT_XOR` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_BOOL_AND` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_BOOL_OR` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_CAT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_CONCAT` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_CONTAINS` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_COSINE_DISTANCE` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_COSINE_SIMILARITY` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_COUNT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_DISTANCE` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_DISTINCT` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_DOT_PRODUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_ELEMENT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_ENTROPY` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_EXTRACT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_FILES` | — | — | — | — | — | — | — | × | — | — | — |
| `LIST_FILTER` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_FIRST` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_GRADE_UP` | E | — | — | — | — | — | — | — | — | — | — |
| `LIST_HAS` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_HAS_ALL` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_HAS_ANY` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_HISTOGRAM` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_INDEXOF` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_INNER_PRODUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_INTERSECT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_KURTOSIS` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_KURTOSIS_POP` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_LAST` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_MAD` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_MAX` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_MEDIAN` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_MIN` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_MODE` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_NEGATIVE_DOT_PRODUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_NEGATIVE_INNER_PRODUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_PACK` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_POSITION` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_PREPEND` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_PRODUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_REDUCE` | E | — | — | — | — | — | — | — | — | — | — |
| `LIST_RESIZE` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_REVERSE` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_REVERSE_SORT` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_SECRETS` | — | — | — | — | — | — | — | × | — | — | — |
| `LIST_SELECT` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_SEM` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_SKEWNESS` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_SLICE` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_SORT` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_STDDEV_POP` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_STDDEV_SAMP` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_STRING_AGG` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_SUM` | E | — | — | — | — | — | — | — | — | — | — |
| `LIST_TRANSFORM` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_UNIQUE` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_VALUE` | S | — | — | — | — | — | — | — | — | — | — |
| `LIST_VAR_POP` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_VAR_SAMP` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_WHERE` | × | — | — | — | — | — | — | — | — | — | — |
| `LIST_ZIP` | E | — | — | — | — | — | — | — | — | — | — |
| `LN` | S | S | S | S | S | S | S | S | S | S | S |
| `LOCALTIME` | S | S | S | S | S | S | S | S | S | S | S |
| `LOCALTIMESTAMP` | S | S | S | S | S | S | S | S | S | S | S |
| `LOCATE` | S | S | S | S | S | S | S | S | S | S | S |
| `LOG` | S | S | S | S | S | S | S | S | S | S | S |
| `LOG10` | S | S | S | S | S | S | S | S | S | S | S |
| `LOG1P` | — | — | — | — | E | — | — | E | — | — | — |
| `LOG2` | S | S | S | S | S | S | S | S | S | S | S |
| `LOGICAL_AND` | S | S | S | S | S | S | S | S | S | S | S |
| `LOGICAL_OR` | S | S | S | S | S | S | S | S | S | S | S |
| `LOGINPROPERTY` | — | — | — | — | — | × | — | — | — | — | — |
| `LOWER` | S | S | S | S | S | S | S | S | S | S | S |
| `LOWER_ATTRIBUTE_NAMES` | — | — | — | — | — | — | — | — | × | — | — |
| `LOWER_HEX` | S | S | S | S | S | S | S | S | S | S | S |
| `LOWER_INC` | — | × | — | — | — | — | — | — | — | — | — |
| `LOWER_INF` | — | × | — | — | — | — | — | — | — | — | — |
| `LPAD` | S | S | S | S | S | S | S | S | S | S | S |
| `LSEG` | — | × | — | — | — | — | — | — | — | — | — |
| `LTRIM` | S | S | S | S | S | S | S | S | S | S | S |
| `LTTB` | × | — | — | — | — | — | — | — | — | — | — |
| `LUHN_CHECK` | — | — | — | — | E | — | — | E | — | E | × |
| `MACADDR8_SET7BIT` | — | × | — | — | — | — | — | — | — | — | — |
| `MAD` | × | — | — | — | — | — | — | — | — | — | — |
| `MAKEACLITEM` | — | × | — | — | — | — | — | — | — | — | — |
| `MAKE_DATE` | S | × | — | — | E | — | — | E | — | — | — |
| `MAKE_DT_INTERVAL` | — | — | — | — | E | — | — | E | — | — | — |
| `MAKE_INTERVAL` | S | S | S | S | S | S | S | S | S | S | S |
| `MAKE_SET_DIGEST` | — | — | — | — | — | — | — | — | — | × | × |
| `MAKE_TIME` | S | S | — | — | — | — | — | × | S | — | — |
| `MAKE_TIMESTAMP` | S | S | — | — | S | — | — | S | S | — | — |
| `MAKE_TIMESTAMPTZ` | × | × | — | — | — | — | — | — | — | — | — |
| `MAKE_TIMESTAMP_LTZ` | — | — | — | — | E | — | — | E | — | — | — |
| `MAKE_TIMESTAMP_MS` | × | — | — | — | — | — | — | — | — | — | — |
| `MAKE_TIMESTAMP_NS` | × | — | — | — | — | — | — | — | — | — | — |
| `MAKE_TIMESTAMP_NTZ` | — | — | — | — | E | — | — | E | — | — | — |
| `MAKE_TYPE` | × | — | — | — | — | — | — | — | — | — | — |
| `MAKE_VALID_UTF8` | — | — | — | — | — | — | — | × | — | — | — |
| `MAKE_YM_INTERVAL` | — | — | — | — | E | — | — | E | — | — | — |
| `MANHATTAN_DISTANCE` | S | S | S | S | S | S | S | S | S | S | S |
| `MAP` | S | S | S | S | S | S | S | S | S | S | S |
| `MAPJOIN` | — | — | — | — | S | — | — | S | — | — | — |
| `MAP_AGG` | — | — | — | — | — | — | — | — | — | × | × |
| `MAP_CAT` | S | S | S | S | S | S | S | S | S | S | S |
| `MAP_CONCAT` | × | — | — | — | E | — | — | E | — | × | × |
| `MAP_CONSTRUCT` | — | — | × | — | — | — | — | — | — | — | — |
| `MAP_CONTAINS` | × | — | — | — | — | — | — | — | — | — | — |
| `MAP_CONTAINS_ENTRY` | × | — | — | — | — | — | — | — | — | — | — |
| `MAP_CONTAINS_KEY` | S | S | S | S | S | S | S | S | S | S | S |
| `MAP_CONTAINS_VALUE` | × | — | — | — | — | — | — | — | — | — | — |
| `MAP_DELETE` | S | S | S | S | S | S | S | S | S | S | S |
| `MAP_ENTRIES` | × | — | × | — | E | — | — | E | — | × | × |
| `MAP_EXTRACT` | × | — | — | — | — | — | — | — | — | — | — |
| `MAP_EXTRACT_VALUE` | × | — | — | — | — | — | — | — | — | — | — |
| `MAP_FILTER` | — | — | — | — | × | — | — | × | — | E | × |
| `MAP_FROM_ARRAYS` | — | — | — | — | S | — | — | S | — | — | — |
| `MAP_FROM_ENTRIES` | S | S | S | S | S | S | S | S | S | S | S |
| `MAP_INSERT` | S | S | S | S | S | S | S | S | S | S | S |
| `MAP_KEYS` | S | S | S | S | S | S | S | S | S | S | S |
| `MAP_PICK` | S | S | S | S | S | S | S | S | S | S | S |
| `MAP_SIZE` | S | S | S | S | S | S | S | S | S | S | S |
| `MAP_UNION` | — | — | — | — | — | — | — | — | — | × | × |
| `MAP_VALUES` | × | — | — | — | E | — | — | E | — | × | × |
| `MAP_ZIP_WITH` | — | — | — | — | × | — | — | × | — | E | × |
| `MASK` | — | — | — | — | E | — | — | E | — | — | — |
| `MASKLEN` | — | × | — | — | — | — | — | — | — | — | — |
| `MATCH` | S | S | S | S | S | S | S | S | S | S | S |
| `MATCH_AGAINST` | S | S | S | S | S | S | S | S | S | S | S |
| `MATCH_NUMBER` | — | — | — | — | — | — | — | × | — | × | — |
| `MATERIALIZED_VIEW_REFRESH_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `MAX` | S | S | S | S | S | S | S | S | S | S | S |
| `MAX_BY` | S | S | S | S | S | S | S | S | S | S | S |
| `MD5` | S | S | S | S | S | S | S | S | S | S | S |
| `MD5_BINARY` | — | — | S | — | — | — | — | — | — | — | — |
| `MD5_DIGEST` | S | S | S | S | S | S | S | S | S | S | S |
| `MD5_HEX` | — | — | S | — | — | — | — | — | — | — | — |
| `MD5_NUMBER` | × | — | — | — | — | — | — | — | — | — | — |
| `MD5_NUMBER_LOWER` | × | — | — | — | — | — | — | — | — | — | — |
| `MD5_NUMBER_LOWER64` | — | — | S | — | — | — | — | — | — | — | — |
| `MD5_NUMBER_UPPER` | × | — | — | — | — | — | — | — | — | — | — |
| `MD5_NUMBER_UPPER64` | — | — | S | — | — | — | — | — | — | — | — |
| `MEAN` | — | — | — | — | E | — | — | E | — | — | — |
| `MEASURE` | — | — | — | — | — | — | — | × | — | — | — |
| `MEDIAN` | S | S | S | S | S | S | S | S | S | S | S |
| `MERGE` | — | — | — | — | S | — | — | S | — | × | × |
| `MERGEJOIN` | — | — | — | — | S | — | — | S | — | — | — |
| `MERGE_ACTION` | — | × | — | — | — | — | — | — | — | — | — |
| `MERGE_SET_DIGEST` | — | — | — | — | — | — | — | — | — | × | × |
| `MICROSECOND` | × | — | — | — | — | — | — | — | — | — | — |
| `MILLENNIUM` | × | — | — | — | — | — | — | — | — | — | — |
| `MILLISECOND` | × | — | — | — | — | — | — | — | — | × | × |
| `MIN` | S | S | S | S | S | S | S | S | S | S | S |
| `MINHASH` | S | S | S | S | S | S | S | S | S | S | S |
| `MINHASH_COMBINE` | S | S | S | S | S | S | S | S | S | S | S |
| `MINUTE` | S | S | S | S | S | S | S | S | S | S | S |
| `MIN_ACTIVE_ROWVERSION` | — | — | — | — | — | × | — | — | — | — | — |
| `MIN_BY` | S | S | S | S | S | S | S | S | S | S | S |
| `MIN_SCALE` | — | × | — | — | — | — | — | — | — | — | — |
| `MISMATCHES` | × | — | — | — | — | — | — | — | — | — | — |
| `MOD` | S | S | S | S | S | S | S | S | S | S | S |
| `MODE` | S | S | S | S | S | S | S | S | S | S | S |
| `MODEL_MONITOR_DRIFT_METRIC` | — | — | × | — | — | — | — | — | — | — | — |
| `MODEL_MONITOR_PERFORMANCE_METRIC` | — | — | × | — | — | — | — | — | — | — | — |
| `MODEL_MONITOR_STAT_METRIC` | — | — | × | — | — | — | — | — | — | — | — |
| `MONOTONICALLY_INCREASING_ID` | — | — | — | — | E | — | — | E | — | — | — |
| `MONTH` | S | S | S | S | S | S | S | S | S | S | S |
| `MONTHNAME` | S | S | S | S | S | S | S | S | S | S | S |
| `MONTHS_BETWEEN` | S | S | S | S | S | S | S | S | S | S | S |
| `MULTIMAP_AGG` | — | — | — | — | — | — | — | — | — | × | × |
| `MULTIMAP_FROM_ENTRIES` | — | — | — | — | — | — | — | — | — | × | × |
| `MULTIPLY` | × | — | — | — | — | — | — | — | — | — | — |
| `MULTIRANGE` | — | × | — | — | — | — | — | — | — | — | — |
| `MURMUR3` | — | — | — | — | — | — | — | — | — | E | E |
| `MURMUR3_32_HASH` | — | — | — | — | — | — | — | — | × | — | — |
| `MXID_AGE` | — | × | — | — | — | — | — | — | — | — | — |
| `M_D5_NUMBER_LOWER64` | S | S | S | S | S | S | S | S | S | S | S |
| `M_D5_NUMBER_UPPER64` | S | S | S | S | S | S | S | S | S | S | S |
| `M_L_FORECAST` | S | S | S | S | S | S | S | S | S | S | S |
| `M_L_TRANSLATE` | S | S | S | S | S | S | S | S | S | S | S |
| `NAMED_STRUCT` | — | — | — | — | S | — | — | S | — | — | — |
| `NAN` | — | — | — | — | — | — | — | — | — | × | × |
| `NANVL` | S | S | S | S | S | S | S | S | S | S | S |
| `NCHAR` | — | — | — | — | — | E | × | — | — | — | — |
| `NEGATIVE` | S | S | S | S | S | S | S | S | S | S | S |
| `NET.HOST` | — | — | — | S | — | — | — | — | — | — | — |
| `NET.IPV4_FROM_INT64` | — | — | — | S | — | — | — | — | — | — | — |
| `NET.IPV4_TO_INT64` | — | — | — | S | — | — | — | — | — | — | — |
| `NET.IP_FROM_STRING` | — | — | — | S | — | — | — | — | — | — | — |
| `NET.IP_NET_MASK` | — | — | — | S | — | — | — | — | — | — | — |
| `NET.IP_TO_STRING` | — | — | — | S | — | — | — | — | — | — | — |
| `NET.IP_TRUNC` | — | — | — | S | — | — | — | — | — | — | — |
| `NET.PUBLIC_SUFFIX` | — | — | — | S | — | — | — | — | — | — | — |
| `NET.REG_DOMAIN` | — | — | — | S | — | — | — | — | — | — | — |
| `NET.SAFE_IP_FROM_STRING` | — | — | — | S | — | — | — | — | — | — | — |
| `NETMASK` | — | × | — | — | — | — | — | — | — | — | — |
| `NETWORK` | — | × | — | — | — | — | — | — | — | — | — |
| `NETWORK_RULE_REFERENCES` | — | — | × | — | — | — | — | — | — | — | — |
| `NET_FUNC` | S | S | S | S | S | S | S | S | S | S | S |
| `NEWID` | — | — | — | — | — | S | S | — | — | — | — |
| `NEWSEQUENTIALID` | — | — | — | — | — | × | — | — | — | — | — |
| `NEXT` | — | — | — | — | — | — | — | × | — | × | — |
| `NEXTAFTER` | × | — | — | — | — | — | — | — | — | — | — |
| `NEXTVAL` | E | E | — | — | — | — | — | — | — | — | — |
| `NEXT_DAY` | S | S | S | S | S | S | S | S | S | S | S |
| `NEXT_VALUE_FOR` | S | S | S | S | S | S | S | S | S | S | S |
| `NFC_NORMALIZE` | × | — | — | — | — | — | — | — | — | — | — |
| `NGRAMS` | — | — | — | — | — | — | — | — | — | × | × |
| `NODES` | — | — | — | × | — | — | — | — | — | — | — |
| `NODE_ID_FROM_PARTS` | — | — | — | — | — | × | — | — | — | — | — |
| `NONE_MATCH` | — | — | — | — | — | — | — | — | — | E | E |
| `NORMAL` | S | S | S | S | S | S | S | S | S | S | S |
| `NORMALIZE` | S | S | S | S | S | S | S | S | S | S | S |
| `NORMALIZED_INTERVAL` | × | — | — | — | — | — | — | — | — | — | — |
| `NORMALIZE_AND_CASEFOLD` | — | — | — | S | — | — | — | — | — | — | — |
| `NORMAL_CDF` | — | — | — | — | — | — | — | — | — | × | × |
| `NOTIFICATION_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `NOT_ILIKE_ESCAPE` | × | — | — | — | — | — | — | — | — | — | — |
| `NOT_LIKE_ESCAPE` | × | — | — | — | — | — | — | — | — | — | — |
| `NOW` | × | S | — | — | E | — | — | S | S | S | S |
| `NPOINTS` | — | × | — | — | — | — | — | — | — | — | — |
| `NTH_VALUE` | S | S | S | S | S | S | S | S | S | S | S |
| `NTILE` | S | S | S | S | S | S | S | S | S | S | S |
| `NULLIF` | S | S | S | S | S | S | S | S | S | S | S |
| `NULLIFZERO` | — | — | S | — | — | — | — | × | — | — | — |
| `NUMBER_TO_STR` | S | S | S | S | S | S | S | S | S | S | S |
| `NUMERIC_HISTOGRAM` | — | — | — | — | — | — | — | — | — | E | × |
| `NUMNODE` | — | × | — | — | — | — | — | — | — | — | — |
| `NUM_NONNULLS` | — | E | — | — | — | — | — | — | — | — | — |
| `NUM_NULLS` | — | E | — | — | — | — | — | — | — | — | — |
| `NVL` | S | S | S | S | S | S | S | S | S | S | S |
| `NVL2` | S | S | S | S | S | S | S | S | S | S | S |
| `OBJ.FETCH_METADATA` | — | — | — | × | — | — | — | — | — | — | — |
| `OBJ.GET_ACCESS_URL` | — | — | — | × | — | — | — | — | — | — | — |
| `OBJ.GET_READ_URL` | — | — | — | × | — | — | — | — | — | — | — |
| `OBJ.LIST` | — | — | — | × | — | — | — | — | — | — | — |
| `OBJ.MAKE_REF` | — | — | — | × | — | — | — | — | — | — | — |
| `OBJECT` | — | — | — | — | — | — | — | — | × | — | — |
| `OBJECTID_TIMESTAMP` | — | — | — | — | — | — | — | — | — | × | — |
| `OBJECTPROPERTY` | — | — | — | — | — | E | × | — | — | — | — |
| `OBJECTPROPERTYEX` | — | — | — | — | — | E | × | — | — | — | — |
| `OBJECT_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `OBJECT_CONSTRUCT` | — | — | S | — | — | — | — | — | — | — | — |
| `OBJECT_CONSTRUCT_KEEP_NULL` | — | — | S | — | — | — | — | — | — | — | — |
| `OBJECT_CONSTRUCT_KEEP_NULL_STRUCTURED` | — | — | × | — | — | — | — | — | — | — | — |
| `OBJECT_DEFINITION` | — | — | — | — | — | × | × | — | — | — | — |
| `OBJECT_DELETE` | — | — | E | — | — | — | — | — | — | — | — |
| `OBJECT_ID` | S | S | S | S | S | S | S | S | S | S | S |
| `OBJECT_ID_FROM_EDGE_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `OBJECT_ID_FROM_NODE_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `OBJECT_INSERT` | S | S | S | S | S | S | S | S | S | S | S |
| `OBJECT_KEYS` | — | — | S | — | — | — | — | — | — | — | — |
| `OBJECT_NAME` | — | — | — | — | — | E | E | — | — | — | — |
| `OBJECT_PICK` | — | — | E | — | — | — | — | — | — | — | — |
| `OBJECT_SCHEMA_NAME` | — | — | — | — | — | E | × | — | — | — | — |
| `OBJECT_TRANSFORM` | S | S | S | S | S | S | S | S | S | S | S |
| `OBJ_DESCRIPTION` | — | × | — | — | — | — | — | — | — | — | — |
| `OCTETINDEX` | — | — | — | — | — | — | — | — | × | — | — |
| `OCTET_LENGTH` | × | × | S | S | E | — | — | E | × | — | — |
| `ONLINE_FEATURE_TABLE_REFRESH_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `OPENDATASOURCE` | — | — | — | — | — | × | — | — | — | — | — |
| `OPENJSON` | S | S | S | S | S | S | S | S | S | S | S |
| `OPENQUERY` | — | — | — | — | — | × | — | — | — | — | — |
| `OPENROWSET` | — | — | — | — | — | × | — | — | — | — | — |
| `OPENXML` | — | — | — | — | — | × | — | — | — | — | — |
| `OPEN_J_S_O_N` | S | S | S | S | S | S | S | S | S | S | S |
| `OR` | S | S | S | S | S | S | S | S | S | S | S |
| `ORD` | × | — | — | — | — | — | — | — | — | — | — |
| `ORIGINAL_DB_NAME` | — | — | — | — | — | × | — | — | — | — | — |
| `ORIGINAL_LOGIN` | — | — | — | — | — | E | — | — | — | — | — |
| `OVERLAY` | S | S | S | S | S | S | S | S | S | S | S |
| `PAD` | S | S | S | S | S | S | S | S | S | S | S |
| `PARAMETERIZED_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `PARSE` | — | — | — | — | — | × | × | — | — | — | — |
| `PARSENAME` | — | — | — | — | — | S | S | — | — | — | — |
| `PARSE_BIGNUMERIC` | S | S | S | S | S | S | S | S | S | S | S |
| `PARSE_DATA_SIZE` | — | — | — | — | — | — | — | — | — | × | × |
| `PARSE_DATE` | — | — | — | S | — | — | — | — | — | — | — |
| `PARSE_DATETIME` | S | S | S | S | S | S | S | S | S | S | S |
| `PARSE_DIRNAME` | × | — | — | — | — | — | — | — | — | — | — |
| `PARSE_DIRPATH` | × | — | — | — | — | — | — | — | — | — | — |
| `PARSE_DURATION` | — | — | — | — | — | — | — | — | — | E | E |
| `PARSE_FILENAME` | × | — | — | — | — | — | — | — | — | — | — |
| `PARSE_FORMATTED_BYTES` | × | — | — | — | — | — | — | — | — | — | — |
| `PARSE_IDENT` | — | × | — | — | — | — | — | — | — | — | — |
| `PARSE_IP` | S | S | S | S | S | S | S | S | S | S | S |
| `PARSE_JSON` | S | S | S | S | S | S | S | B | B | S | S |
| `PARSE_NUMERIC` | S | S | S | S | S | S | S | S | S | S | S |
| `PARSE_PATH` | × | — | — | — | — | — | — | — | — | — | — |
| `PARSE_TIME` | S | S | S | S | S | S | S | S | S | S | S |
| `PARSE_TIMESTAMP` | — | — | — | S | — | — | — | × | — | — | — |
| `PARSE_URL` | S | S | S | S | S | S | S | S | S | S | S |
| `PARSE_XML` | — | — | × | — | — | — | — | — | — | — | — |
| `PATH` | — | × | — | — | — | — | — | — | — | — | — |
| `PATH_FIRST` | — | — | — | × | — | — | — | — | — | — | — |
| `PATH_LAST` | — | — | — | × | — | — | — | — | — | — | — |
| `PATH_LENGTH` | — | — | — | × | — | — | — | — | — | — | — |
| `PATINDEX` | — | — | — | — | — | E | E | — | — | — | — |
| `PCLOSE` | — | × | — | — | — | — | — | — | — | — | — |
| `PERCENTILE` | — | — | — | — | S | — | — | S | — | — | — |
| `PERCENTILE_APPROX` | — | — | — | — | S | — | — | S | — | — | — |
| `PERCENTILE_CONT` | S | S | S | S | S | S | S | S | S | S | S |
| `PERCENTILE_DISC` | S | S | S | S | S | S | S | S | S | S | S |
| `PERCENT_RANK` | S | S | S | S | S | S | S | S | S | S | S |
| `PERIOD_BEGIN` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_CONSTRUCT` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_CONTAINS` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_END` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_EQUALS` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_IMMEDIATELY_PRECEDES` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_IMMEDIATELY_SUCCEEDS` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_INTERSECT` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_LDIFF` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_MEETS` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_OVERLAPS` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_PRECEDES` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_RDIFF` | — | — | × | — | — | — | — | — | — | — | — |
| `PERIOD_SUCCEEDS` | — | — | × | — | — | — | — | — | — | — | — |
| `PERMISSIONS` | — | — | — | — | — | E | — | — | — | — | — |
| `PERMUTE` | — | — | — | — | — | — | — | — | — | × | — |
| `PG_ADVISORY_LOCK` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_ADVISORY_LOCK_SHARED` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_ADVISORY_UNLOCK` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_ADVISORY_UNLOCK_ALL` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_ADVISORY_UNLOCK_SHARED` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_ADVISORY_XACT_LOCK` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_ADVISORY_XACT_LOCK_SHARED` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_AVAILABLE_WAL_SUMMARIES` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_BACKEND_PID` | — | E | — | — | — | — | — | — | × | — | — |
| `PG_BACKUP_START` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_BACKUP_STOP` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_BASETYPE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_BLOCKING_PIDS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CANCEL_BACKEND` | — | × | — | — | — | — | — | — | × | — | — |
| `PG_CHAR_TO_ENCODING` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CLEAR_ATTRIBUTE_STATS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CLEAR_RELATION_STATS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CLIENT_ENCODING` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_COLLATION_ACTUAL_VERSION` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_COLLATION_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_COLUMN_COMPRESSION` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_COLUMN_SIZE` | — | E | — | — | — | — | — | — | — | — | — |
| `PG_COLUMN_TOAST_CHUNK_ID` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CONF_LOAD_TIME` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CONTROL_CHECKPOINT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CONTROL_INIT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CONTROL_RECOVERY` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CONTROL_SYSTEM` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CONVERSION_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_COPY_LOGICAL_REPLICATION_SLOT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_COPY_PHYSICAL_REPLICATION_SLOT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CREATE_LOGICAL_REPLICATION_SLOT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CREATE_PHYSICAL_REPLICATION_SLOT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CREATE_RESTORE_POINT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CURRENT_LOGFILE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CURRENT_SNAPSHOT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CURRENT_WAL_FLUSH_LSN` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CURRENT_WAL_INSERT_LSN` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CURRENT_WAL_LSN` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CURRENT_XACT_ID` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_CURRENT_XACT_ID_IF_ASSIGNED` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_DATABASE_COLLATION_ACTUAL_VERSION` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_DATABASE_SIZE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_DESCRIBE_OBJECT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_DROP_REPLICATION_SLOT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_ENCODING_TO_CHAR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_EVENT_TRIGGER_DDL_COMMANDS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_EVENT_TRIGGER_DROPPED_OBJECTS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_EVENT_TRIGGER_TABLE_REWRITE_OID` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_EVENT_TRIGGER_TABLE_REWRITE_REASON` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_EXPORT_SNAPSHOT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_FILENODE_RELATION` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_FUNCTION_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_ACL` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_CATALOG_FOREIGN_KEYS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_COLS` | — | — | — | — | — | — | — | — | × | — | — |
| `PG_GET_CONSTRAINTDEF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_EXPR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_FUNCTIONDEF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_FUNCTION_ARGUMENTS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_FUNCTION_IDENTITY_ARGUMENTS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_FUNCTION_RESULT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_GRANTEE_BY_IAM_ROLE` | — | — | — | — | — | — | — | — | × | — | — |
| `PG_GET_IAM_ROLE_BY_USER` | — | — | — | — | — | — | — | — | × | — | — |
| `PG_GET_INDEXDEF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_KEYWORDS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_LATE_BINDING_VIEW_COLS` | — | — | — | — | — | — | — | — | × | — | — |
| `PG_GET_LOADED_MODULES` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_MULTIXACT_MEMBERS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_OBJECT_ADDRESS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_OWNED_SEQUENCE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_PARTITION_CONSTRAINTDEF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_PARTKEYDEF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_RULEDEF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_SERIAL_SEQUENCE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_SESSION_ROLES` | — | — | — | — | — | — | — | — | × | — | — |
| `PG_GET_STATISTICSOBJDEF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_TRIGGERDEF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_USERBYID` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_VIEWDEF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_WAL_REPLAY_PAUSE_STATE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_WAL_RESOURCE_MANAGERS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_GET_WAL_SUMMARIZER_STATE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_HAS_ROLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_IDENTIFY_OBJECT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_IDENTIFY_OBJECT_AS_ADDRESS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_IMPORT_SYSTEM_COLLATIONS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_INDEXAM_HAS_PROPERTY` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_INDEXES_SIZE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_INDEX_COLUMN_HAS_PROPERTY` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_INDEX_HAS_PROPERTY` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_INPUT_ERROR_INFO` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_INPUT_IS_VALID` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_IS_IN_RECOVERY` | — | E | — | — | — | — | — | — | — | — | — |
| `PG_IS_OTHER_TEMP_SCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_IS_WAL_REPLAY_PAUSED` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_JIT_AVAILABLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LAST_COMMITTED_XACT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LAST_COPY_COUNT` | — | — | — | — | — | — | — | — | × | — | — |
| `PG_LAST_COPY_ID` | — | — | — | — | — | — | — | — | × | — | — |
| `PG_LAST_QUERY_ID` | — | — | — | — | — | — | — | — | E | — | — |
| `PG_LAST_UNLOAD_COUNT` | — | — | — | — | — | — | — | — | × | — | — |
| `PG_LAST_UNLOAD_ID` | — | — | — | — | — | — | — | — | × | — | — |
| `PG_LAST_WAL_RECEIVE_LSN` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LAST_WAL_REPLAY_LSN` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LAST_XACT_REPLAY_TIMESTAMP` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LISTENING_CHANNELS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LOGICAL_EMIT_MESSAGE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LOGICAL_SLOT_GET_BINARY_CHANGES` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LOGICAL_SLOT_GET_CHANGES` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LOGICAL_SLOT_PEEK_BINARY_CHANGES` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LOGICAL_SLOT_PEEK_CHANGES` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LOG_BACKEND_MEMORY_CONTEXTS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LOG_STANDBY_SNAPSHOT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LS_ARCHIVE_STATUSDIR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LS_DIR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LS_LOGDIR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LS_LOGICALMAPDIR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LS_LOGICALSNAPDIR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LS_REPLSLOTDIR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LS_SUMMARIESDIR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LS_TMPDIR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_LS_WALDIR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_MCV_LIST_ITEMS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_MY_TEMP_SCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_NOTIFICATION_QUEUE_USAGE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_NOTIFY` | — | E | — | — | — | — | — | — | — | — | — |
| `PG_NUMA_AVAILABLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_OPCLASS_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_OPERATOR_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_OPFAMILY_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_OPTIONS_TO_TABLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_PARTITION_ANCESTORS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_PARTITION_ROOT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_PARTITION_TREE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_POSTMASTER_START_TIME` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_PROMOTE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_READ_BINARY_FILE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_READ_FILE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_RELATION_FILENODE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_RELATION_FILEPATH` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_RELATION_SIZE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_RELOAD_CONF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_ADVANCE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_CREATE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_DROP` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_OID` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_PROGRESS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_SESSION_IS_SETUP` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_SESSION_PROGRESS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_SESSION_RESET` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_SESSION_SETUP` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_XACT_RESET` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_ORIGIN_XACT_SETUP` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_REPLICATION_SLOT_ADVANCE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_RESTORE_ATTRIBUTE_STATS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_RESTORE_RELATION_STATS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_ROTATE_LOGFILE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SAFE_SNAPSHOT_BLOCKING_PIDS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SETTINGS_GET_FLAGS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SIZE_BYTES` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SIZE_PRETTY` | — | E | — | — | — | — | — | — | — | — | — |
| `PG_SLEEP` | — | E | — | — | — | — | — | — | — | — | — |
| `PG_SLEEP_FOR` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SLEEP_UNTIL` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SNAPSHOT_XIP` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SNAPSHOT_XMAX` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SNAPSHOT_XMIN` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SPLIT_WALFILE_NAME` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_STATISTICS_OBJ_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_STAT_FILE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SWITCH_WAL` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_SYNC_REPLICATION_SLOTS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TABLESPACE_DATABASES` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TABLESPACE_LOCATION` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TABLESPACE_SIZE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TABLE_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TABLE_SIZE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TERMINATE_BACKEND` | — | × | — | — | — | — | — | — | × | — | — |
| `PG_TOTAL_RELATION_SIZE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TRIGGER_DEPTH` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TRY_ADVISORY_LOCK` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TRY_ADVISORY_LOCK_SHARED` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TRY_ADVISORY_XACT_LOCK` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TRY_ADVISORY_XACT_LOCK_SHARED` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TS_CONFIG_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TS_DICT_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TS_PARSER_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TS_TEMPLATE_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_TYPEOF` | E | E | — | — | — | — | — | — | — | — | — |
| `PG_TYPE_IS_VISIBLE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_VISIBLE_IN_SNAPSHOT` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_WALFILE_NAME` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_WALFILE_NAME_OFFSET` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_WAL_LSN_DIFF` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_WAL_REPLAY_PAUSE` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_WAL_REPLAY_RESUME` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_WAL_SUMMARY_CONTENTS` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_XACT_COMMIT_TIMESTAMP` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_XACT_COMMIT_TIMESTAMP_ORIGIN` | — | × | — | — | — | — | — | — | — | — | — |
| `PG_XACT_STATUS` | — | × | — | — | — | — | — | — | — | — | — |
| `PHRASETO_TSQUERY` | — | × | — | — | — | — | — | — | — | — | — |
| `PI` | S | S | S | S | S | S | S | S | S | S | S |
| `PIPE_USAGE_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `PLAINTO_TSQUERY` | — | × | — | — | — | — | — | — | — | — | — |
| `PMOD` | — | — | — | — | E | — | — | E | — | — | — |
| `POINT` | — | × | — | — | — | — | — | — | — | — | — |
| `POLICY_CONTEXT` | — | — | × | — | — | — | — | — | — | — | — |
| `POLICY_REFERENCES` | — | — | × | — | — | — | — | — | — | — | — |
| `POLYGON` | — | × | — | — | — | — | — | — | — | — | — |
| `POPEN` | — | × | — | — | — | — | — | — | — | — | — |
| `POSEXPLODE` | S | S | S | S | S | S | S | S | S | S | S |
| `POSEXPLODE_OUTER` | S | S | S | S | S | S | S | S | S | S | S |
| `POSITION` | S | S | S | S | S | S | S | S | S | S | S |
| `POSITIVE` | — | — | — | — | E | — | — | E | — | — | — |
| `POW` | S | S | S | S | S | S | S | S | S | S | S |
| `POWER` | S | S | S | S | S | S | S | S | S | S | S |
| `PQSERVERVERSION` | — | × | — | — | — | — | — | — | — | — | — |
| `PREDICT` | S | S | — | S | S | S | S | S | S | S | S |
| `PREFIX` | × | — | — | — | — | — | — | — | — | — | — |
| `PREV` | — | — | — | — | — | — | — | × | — | × | — |
| `PREVIOUS_DAY` | S | S | S | S | S | S | S | S | S | S | S |
| `PRINTF` | × | — | — | — | E | — | — | E | — | — | — |
| `PRODUCT` | × | — | — | — | — | × | × | — | — | — | — |
| `PROMPT` | — | — | × | — | — | — | — | — | — | — | — |
| `PWDCOMPARE` | — | — | — | — | — | × | — | — | — | — | — |
| `PWDENCRYPT` | — | — | — | — | — | × | — | — | — | — | — |
| `QDIGEST_AGG` | — | — | — | — | — | — | — | — | — | × | × |
| `QUANTILE` | S | S | S | S | S | S | S | S | S | S | S |
| `QUANTILE_AT_VALUE` | — | — | — | — | — | — | — | — | — | — | × |
| `QUANTILE_CONT` | S | — | — | — | — | — | — | — | — | — | — |
| `QUANTILE_DISC` | S | — | — | — | — | — | — | — | — | — | — |
| `QUARTER` | S | S | S | S | S | S | S | S | S | S | S |
| `QUERY` | × | — | — | — | — | — | — | — | — | — | — |
| `QUERYTREE` | — | × | — | — | — | — | — | — | — | — | — |
| `QUERY_ACCELERATION_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `QUERY_TABLE` | × | — | — | — | — | — | — | — | — | — | — |
| `QUERY_TO_XML` | — | × | — | — | — | — | — | — | — | — | — |
| `QUERY_TO_XMLSCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `QUERY_TO_XML_AND_XMLSCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `QUOTENAME` | — | — | — | — | — | E | E | — | — | — | — |
| `QUOTE_IDENT` | — | × | — | — | — | — | — | — | × | — | — |
| `QUOTE_LITERAL` | — | × | — | — | — | — | — | — | × | — | — |
| `QUOTE_NULLABLE` | — | × | — | — | — | — | — | — | — | — | — |
| `RADIANS` | S | S | S | S | S | S | S | S | S | S | S |
| `RADIUS` | — | × | — | — | — | — | — | — | — | — | — |
| `RAISE_ERROR` | — | — | — | — | × | — | — | × | — | — | — |
| `RAND` | S | S | S | S | S | S | S | S | S | S | S |
| `RANDN` | S | S | S | S | S | S | S | S | S | S | S |
| `RANDOM` | S | S | S | S | S | S | S | S | S | S | S |
| `RANDOM_NORMAL` | — | × | — | — | — | — | — | — | — | — | — |
| `RANDOM_STRING` | — | — | — | — | — | — | — | — | — | × | — |
| `RANDSTR` | S | S | S | S | S | S | S | S | S | S | S |
| `RANGE` | S | — | — | × | — | — | — | × | — | — | — |
| `RANGE_AGG` | — | × | — | — | — | — | — | — | — | — | — |
| `RANGE_BUCKET` | S | S | S | S | S | S | S | S | S | S | S |
| `RANGE_CONTAINS` | — | — | — | × | — | — | — | — | — | — | — |
| `RANGE_END` | — | — | — | E | — | — | — | — | — | — | — |
| `RANGE_INTERSECT` | — | — | — | × | — | — | — | — | — | — | — |
| `RANGE_INTERSECT_AGG` | — | × | — | — | — | — | — | — | — | — | — |
| `RANGE_MERGE` | — | × | — | — | — | — | — | — | — | — | — |
| `RANGE_N` | S | S | S | S | S | S | S | S | S | S | S |
| `RANGE_OVERLAPS` | — | — | — | × | — | — | — | — | — | — | — |
| `RANGE_SESSIONIZE` | — | — | — | × | — | — | — | — | — | — | — |
| `RANGE_START` | — | — | — | E | — | — | — | — | — | — | — |
| `RANK` | S | S | S | S | S | S | S | S | S | S | S |
| `RATIO_TO_REPORT` | — | — | × | — | — | — | — | — | — | — | — |
| `READ_BLOB` | × | — | — | — | — | — | — | — | — | — | — |
| `READ_CSV` | S | S | S | S | S | S | S | S | S | S | S |
| `READ_FILES` | — | — | — | — | — | — | — | × | — | — | — |
| `READ_KAFKA` | — | — | — | — | — | — | — | × | — | — | — |
| `READ_KINESIS` | — | — | — | — | — | — | — | × | — | — | — |
| `READ_PARQUET` | S | S | S | S | S | S | S | S | S | S | S |
| `READ_PUBSUB` | — | — | — | — | — | — | — | × | — | — | — |
| `READ_PULSAR` | — | — | — | — | — | — | — | × | — | — | — |
| `READ_STATESTORE` | — | — | — | — | — | — | — | × | — | — | — |
| `READ_STATE_METADATA` | — | — | — | — | — | — | — | × | — | — | — |
| `READ_TEXT` | × | — | — | — | — | — | — | — | — | — | — |
| `REBOOT_CLUSTER` | — | — | — | — | — | — | — | — | × | — | — |
| `REDUCE` | S | S | S | S | S | S | S | S | S | S | S |
| `REDUCE_AGG` | — | — | — | — | — | — | — | — | — | × | × |
| `REFLECT` | — | — | — | — | E | — | — | E | — | — | — |
| `REGEXP` | — | — | — | — | E | — | — | — | — | — | — |
| `REGEXP_CONTAINS` | — | — | — | S | — | — | — | — | — | — | — |
| `REGEXP_COUNT` | S | S | S | S | S | S | S | S | S | S | S |
| `REGEXP_ESCAPE` | E | — | — | — | — | — | — | — | — | — | — |
| `REGEXP_EXTRACT` | S | S | S | S | S | S | S | S | S | S | S |
| `REGEXP_EXTRACT_ALL` | S | S | S | S | S | S | S | S | S | S | S |
| `REGEXP_EXTRACT_GROUPS` | — | — | — | × | — | — | — | — | — | — | — |
| `REGEXP_FULL_MATCH` | S | S | S | S | S | S | S | S | S | S | S |
| `REGEXP_INSTR` | S | S | S | S | S | S | S | S | S | S | S |
| `REGEXP_I_LIKE` | S | S | S | S | S | S | S | S | S | S | S |
| `REGEXP_LIKE` | S | S | S | S | S | S | S | S | S | S | S |
| `REGEXP_MATCH` | — | × | — | — | — | — | — | — | — | — | — |
| `REGEXP_MATCHES` | S | × | — | — | — | × | — | — | — | — | — |
| `REGEXP_POSITION` | — | — | — | — | — | — | — | — | — | × | × |
| `REGEXP_REPLACE` | S | S | S | S | S | S | S | S | S | S | S |
| `REGEXP_SPLIT` | S | S | S | S | S | S | S | S | S | S | S |
| `REGEXP_SPLIT_TO_ARRAY` | × | × | — | — | — | — | — | — | — | — | — |
| `REGEXP_SPLIT_TO_TABLE` | × | × | — | — | — | — | — | — | — | — | — |
| `REGEXP_SUBSTR` | S | S | S | S | S | S | S | S | S | S | S |
| `REGEXP_SUBSTR_ALL` | — | — | S | — | — | — | — | — | — | — | — |
| `REGRESS` | — | — | — | — | — | — | — | — | — | × | × |
| `REGR_AVGX` | S | S | S | S | S | S | S | S | S | S | S |
| `REGR_AVGY` | S | S | S | S | S | S | S | S | S | S | S |
| `REGR_COUNT` | S | S | S | S | S | S | S | S | S | S | S |
| `REGR_INTERCEPT` | S | S | S | S | S | S | S | S | S | S | S |
| `REGR_R2` | S | S | S | S | S | S | S | S | S | S | S |
| `REGR_SLOPE` | S | S | S | S | S | S | S | S | S | S | S |
| `REGR_SXX` | S | S | S | S | S | S | S | S | S | S | S |
| `REGR_SXY` | S | S | S | S | S | S | S | S | S | S | S |
| `REGR_SYY` | S | S | S | S | S | S | S | S | S | S | S |
| `REGR_VALX` | S | S | S | S | S | S | S | S | S | S | S |
| `REGR_VALY` | S | S | S | S | S | S | S | S | S | S | S |
| `REG_DOMAIN` | S | S | S | S | S | S | S | S | S | S | S |
| `REMAP_STRUCT` | × | — | — | — | — | — | — | — | — | — | — |
| `REMOTE_QUERY` | — | — | — | — | — | — | — | × | — | — | — |
| `RENDER` | — | — | — | — | — | — | — | — | — | × | × |
| `REPEAT` | B | S | S | S | S | S | S | S | S | S | S |
| `REPEAT_ROW` | × | — | — | — | — | — | — | — | — | — | — |
| `REPLACE` | S | S | S | S | S | S | S | S | S | S | S |
| `REPLACE_TYPE` | × | — | — | — | — | — | — | — | — | — | — |
| `REPLICATE` | — | — | — | — | — | S | S | — | × | — | — |
| `REPLICATION_GROUP_DANGLING_REFERENCES` | — | — | × | — | — | — | — | — | — | — | — |
| `REPLICATION_GROUP_LAG_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `REPLICATION_GROUP_USAGE_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `REPLICATION_USAGE_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `REST_EVENT_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `RESULT_SCAN` | — | — | E | — | — | — | — | — | — | — | — |
| `REVERSE` | S | S | S | S | S | S | S | S | S | S | S |
| `RGB` | — | — | — | — | — | — | — | — | — | × | × |
| `RIGHT` | S | S | S | S | S | S | S | S | S | S | S |
| `RIGHTPAD` | S | S | S | S | S | S | S | S | S | S | S |
| `RIGHT_GRAPHEME` | × | — | — | — | — | — | — | — | — | — | — |
| `RIGHT_SHIFT` | — | — | — | — | — | E | × | — | — | — | — |
| `RINT` | S | S | S | S | S | S | S | S | S | S | S |
| `RLIKE` | — | — | S | — | S | — | — | S | — | — | — |
| `ROLE_IS_MEMBER_OF` | — | — | — | — | — | — | — | — | × | — | — |
| `ROUND` | B | S | S | S | S | S | S | S | S | S | S |
| `ROUNDBANKERS` | × | — | — | — | — | — | — | — | — | — | — |
| `ROUND_EVEN` | × | — | — | — | — | — | — | — | — | — | — |
| `ROW` | × | — | — | — | — | — | — | — | — | S | S |
| `ROWCOUNT_BIG` | — | — | — | — | — | × | — | — | — | — | — |
| `ROW_NUMBER` | S | S | S | S | S | S | S | S | S | S | S |
| `ROW_SECURITY_ACTIVE` | — | × | — | — | — | — | — | — | — | — | — |
| `ROW_TO_JSON` | — | × | — | — | — | — | — | — | — | — | — |
| `RPAD` | S | S | S | S | S | S | S | S | S | S | S |
| `RTRIM` | S | S | S | S | S | S | S | S | S | S | S |
| `RTRIMMED_LENGTH` | S | S | S | S | S | S | S | S | S | S | S |
| `S2_CELLIDFROMPOINT` | — | — | — | × | — | — | — | — | — | — | — |
| `S2_COVERINGCELLIDS` | — | — | — | × | — | — | — | — | — | — | — |
| `SAFE_ADD` | S | S | S | S | S | S | S | S | S | S | S |
| `SAFE_CAST` | S | S | S | S | S | S | S | S | S | S | S |
| `SAFE_CONVERT_BYTES_TO_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `SAFE_DIVIDE` | S | S | S | S | S | S | S | S | S | S | S |
| `SAFE_FUNC` | S | S | S | S | S | S | S | S | S | S | S |
| `SAFE_MULTIPLY` | S | S | S | S | S | S | S | S | S | S | S |
| `SAFE_NEGATE` | S | S | S | S | S | S | S | S | S | S | S |
| `SAFE_SUBTRACT` | S | S | S | S | S | S | S | S | S | S | S |
| `SANITIZE_WEBHOOK_CONTENT` | — | — | × | — | — | — | — | — | — | — | — |
| `SCALE` | — | × | — | — | — | — | — | — | — | — | — |
| `SCHEDULED_TIME` | — | — | × | — | — | — | — | — | — | — | — |
| `SCHEMA_ID` | — | — | — | — | — | E | × | — | — | — | — |
| `SCHEMA_NAME` | — | — | — | — | — | S | S | — | — | — | — |
| `SCHEMA_OF_AVRO` | — | — | — | — | — | — | — | × | — | — | — |
| `SCHEMA_OF_CSV` | — | — | — | — | E | — | — | E | — | — | — |
| `SCHEMA_OF_JSON` | — | — | — | — | E | — | — | E | — | — | — |
| `SCHEMA_OF_JSON_AGG` | — | — | — | — | — | — | — | E | — | — | — |
| `SCHEMA_OF_VARIANT` | — | — | — | — | — | — | — | E | — | — | — |
| `SCHEMA_OF_VARIANT_AGG` | — | — | — | — | — | — | — | E | — | — | — |
| `SCHEMA_OF_XML` | — | — | — | — | — | — | — | E | — | — | — |
| `SCHEMA_TO_XML` | — | × | — | — | — | — | — | — | — | — | — |
| `SCHEMA_TO_XMLSCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `SCHEMA_TO_XML_AND_XMLSCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `SCOPE_IDENTITY` | — | — | — | — | — | E | — | — | — | — | — |
| `SCOPE_RESOLUTION` | S | S | S | S | S | S | S | S | S | S | S |
| `SEARCH` | S | S | S | × | S | S | S | S | S | S | S |
| `SEARCH_IP` | S | S | S | S | S | S | S | S | S | S | S |
| `SEARCH_OPTIMIZATION_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `SEC` | S | S | S | S | S | S | S | S | S | S | S |
| `SECH` | S | S | S | S | S | S | S | S | S | S | S |
| `SECOND` | S | S | S | S | S | S | S | S | S | S | S |
| `SECRET` | S | S | S | S | S | S | S | S | S | S | S |
| `SECURE_CONTEXT` | — | — | — | × | — | — | — | — | — | — | — |
| `SEM` | × | — | — | — | — | — | — | — | — | — | — |
| `SEMANTIC_VIEW` | — | — | S | — | — | — | — | — | — | — | — |
| `SEMANTIC_VIEW_MATERIALIZATION_REFRESH_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `SENTENCES` | — | — | — | — | E | — | — | E | — | — | — |
| `SENTIMENT` | — | — | × | — | — | — | — | — | — | — | — |
| `SEQ1` | S | S | S | S | S | S | S | S | S | S | S |
| `SEQ2` | S | S | S | S | S | S | S | S | S | S | S |
| `SEQ4` | S | S | S | S | S | S | S | S | S | S | S |
| `SEQ8` | S | S | S | S | S | S | S | S | S | S | S |
| `SEQUENCE` | — | — | — | — | S | — | — | S | — | S | S |
| `SERVERLESS_ALERT_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `SERVERLESS_TASK_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `SERVERPROPERTY` | — | — | — | — | — | E | × | — | — | — | — |
| `SESSIONPROPERTY` | — | — | — | — | — | × | — | — | — | — | — |
| `SESSION_CONTEXT` | — | — | — | — | — | E | × | — | — | — | — |
| `SESSION_ID` | — | — | — | — | — | × | — | — | — | — | — |
| `SESSION_USER` | S | S | S | S | S | S | S | S | S | S | S |
| `SESSION_WINDOW` | — | — | — | — | E | — | — | E | — | — | — |
| `SETSEED` | E | × | — | — | — | — | — | — | — | — | — |
| `SETVAL` | — | E | — | — | — | — | — | — | — | — | — |
| `SETWEIGHT` | — | × | — | — | — | — | — | — | — | — | — |
| `SET_AGG` | — | — | — | — | — | — | — | — | — | S | S |
| `SET_BIT` | × | × | — | — | — | E | E | — | — | — | — |
| `SET_BYTE` | — | × | — | — | — | — | — | — | — | — | — |
| `SET_CONFIG` | — | E | — | — | — | — | — | — | × | — | — |
| `SET_MASKLEN` | — | × | — | — | — | — | — | — | — | — | — |
| `SET_SYS_CONTEXT` | — | — | × | — | — | — | — | — | — | — | — |
| `SHA` | S | S | S | S | S | S | S | S | S | S | S |
| `SHA1` | S | S | S | S | S | S | S | S | S | S | S |
| `SHA1_BINARY` | — | — | S | — | — | — | — | — | — | — | — |
| `SHA1_HEX` | — | — | S | — | — | — | — | — | — | — | — |
| `SHA2` | S | S | S | S | S | S | S | S | S | S | S |
| `SHA224` | — | × | — | — | — | — | — | — | — | — | — |
| `SHA256` | S | S | — | S | — | — | — | — | S | S | S |
| `SHA2_BINARY` | — | — | S | — | — | — | — | — | — | — | — |
| `SHA2_HEX` | — | — | S | — | — | — | — | — | — | — | — |
| `SHA384` | — | S | — | — | — | — | — | — | S | — | — |
| `SHA512` | — | S | — | S | — | — | — | — | S | S | S |
| `SHIFTLEFT` | — | — | — | — | S | — | — | S | — | — | — |
| `SHIFTRIGHT` | — | — | — | — | S | — | — | S | — | — | — |
| `SHIFTRIGHTUNSIGNED` | — | — | — | — | E | — | — | E | — | — | — |
| `SHOBJ_DESCRIPTION` | — | × | — | — | — | — | — | — | — | — | — |
| `SHOW_PYTHON_PACKAGES_DEPENDENCIES` | — | — | × | — | — | — | — | — | — | — | — |
| `SHUFFLE` | S | S | S | S | S | S | S | S | S | S | S |
| `SHUFFLEMERGE` | — | — | — | — | S | — | — | S | — | — | — |
| `SHUFFLE_HASH` | — | — | — | — | S | — | — | S | — | — | — |
| `SHUFFLE_REPLICATE_NL` | — | — | — | — | S | — | — | S | — | — | — |
| `SIGN` | B | S | S | S | S | S | S | S | S | S | S |
| `SIGNBIT` | × | — | — | — | — | — | — | — | — | — | — |
| `SIGNBYASYMKEY` | — | — | — | — | — | × | — | — | — | — | — |
| `SIGNBYCERT` | — | — | — | — | — | × | — | — | — | — | — |
| `SIGNUM` | B | S | S | S | S | S | S | S | S | S | S |
| `SIMILARITY` | — | — | — | S | — | — | — | — | — | — | — |
| `SIMPLIFY_GEOMETRY` | — | — | — | — | — | — | — | — | — | × | × |
| `SIN` | S | S | S | S | S | S | S | S | S | S | S |
| `SIND` | — | × | — | — | — | — | — | — | — | — | — |
| `SINH` | S | S | S | S | S | S | S | S | S | S | S |
| `SIZE` | — | — | — | — | S | — | — | S | × | — | — |
| `SKEW` | — | — | S | — | — | — | — | — | — | — | — |
| `SKEWNESS` | S | S | S | S | S | S | S | S | S | S | S |
| `SLEEP_MS` | × | — | — | — | — | — | — | — | — | — | — |
| `SLICE` | — | — | — | — | S | — | — | S | — | S | S |
| `SLOPE` | — | × | — | — | — | — | — | — | — | — | — |
| `SMALLDATETIMEFROMPARTS` | — | — | — | — | — | E | × | — | — | — | — |
| `SMALLINT` | — | — | — | — | E | — | — | E | — | — | — |
| `SOME` | — | × | — | — | E | — | — | E | — | — | — |
| `SORT_ARRAY` | S | S | S | S | S | S | S | S | S | S | S |
| `SOUNDEX` | S | S | S | S | S | S | S | S | B | S | S |
| `SOUNDEX_P123` | S | S | S | S | S | S | S | S | S | S | S |
| `SOURCE_NODE_ID` | — | — | — | × | — | — | — | — | — | — | — |
| `SPACE` | S | S | S | S | S | S | S | S | S | S | S |
| `SPARK_PARTITION_ID` | — | — | — | — | E | — | — | × | — | — | — |
| `SPATIAL_PARTITIONING` | — | — | — | — | — | — | — | — | — | × | × |
| `SPATIAL_PARTITIONS` | — | — | — | — | — | — | — | — | — | × | × |
| `SPLIT` | S | S | S | S | S | S | S | S | S | S | S |
| `SPLIT_BY_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `SPLIT_PART` | S | S | S | S | S | S | S | S | S | S | S |
| `SPLIT_TO_ARRAY` | — | — | — | — | — | — | — | — | S | — | — |
| `SPLIT_TO_MAP` | — | — | — | — | — | — | — | — | — | S | S |
| `SPLIT_TO_MULTIMAP` | — | — | — | — | — | — | — | — | — | × | × |
| `SPLIT_TO_TABLE` | S | S | S | S | S | S | S | S | S | S | S |
| `SPOOKY_HASH_V2_32` | — | — | — | — | — | — | — | — | — | × | × |
| `SPOOKY_HASH_V2_64` | — | — | — | — | — | — | — | — | — | × | × |
| `SPRINTF` | — | × | — | — | — | — | — | — | — | — | — |
| `SQL_KEYWORDS` | — | — | — | — | — | — | — | × | — | — | — |
| `SQL_TOKENIZE` | × | — | — | — | — | — | — | — | — | — | — |
| `SQL_VARIANT_PROPERTY` | — | — | — | — | — | × | — | — | — | — | — |
| `SQRT` | S | S | S | S | S | S | S | S | S | S | S |
| `SQUARE` | — | — | S | — | — | S | S | — | — | — | — |
| `STACK` | S | S | S | S | S | S | S | S | S | S | S |
| `STAGE_DIRECTORY_FILE_REGISTRATION_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `STAGE_STORAGE_USAGE_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `STANDARD_HASH` | S | S | S | S | S | S | S | S | S | S | S |
| `STARTSWITH` | S | S | S | S | S | S | S | S | S | S | S |
| `STARTS_WITH` | S | S | S | S | S | S | S | S | S | S | S |
| `STAR_MAP` | S | S | S | S | S | S | S | S | S | S | S |
| `STATEMENT_TIMESTAMP` | — | E | — | — | — | — | — | — | — | — | — |
| `STATS` | E | — | — | — | — | — | — | — | — | — | — |
| `STATS_DATE` | — | — | — | — | — | × | × | — | — | — | — |
| `STD` | — | — | — | — | E | — | — | E | — | — | — |
| `STDDEV` | S | B | S | S | S | S | S | S | S | S | S |
| `STDDEV_POP` | S | B | S | S | S | S | S | S | S | S | S |
| `STDDEV_SAMP` | S | B | S | S | S | S | S | S | S | S | S |
| `STDEV` | S | B | S | S | S | S | S | S | S | S | S |
| `STDEVP` | — | — | — | — | — | × | × | — | — | — | — |
| `STORAGE_LIFECYCLE_POLICY_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `STR` | — | — | — | — | — | × | × | — | — | — | — |
| `STRFTIME` | S | — | — | — | — | — | — | — | — | — | — |
| `STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `STRINGAGG` | S | — | — | — | — | — | — | — | — | — | — |
| `STRING_AGG` | S | S | S | S | S | S | S | S | S | S | S |
| `STRING_ESCAPE` | — | — | — | — | — | E | E | — | — | — | — |
| `STRING_SPLIT` | S | — | — | — | — | E | E | — | — | — | — |
| `STRING_SPLIT_REGEX` | S | — | — | — | — | — | — | — | — | — | — |
| `STRING_TO_ARRAY` | S | S | S | S | S | S | S | S | S | S | S |
| `STRING_TO_TABLE` | — | × | — | — | — | — | — | — | — | — | — |
| `STRIP` | — | × | — | — | — | — | — | — | — | — | — |
| `STRIP_ACCENTS` | × | — | — | — | — | — | — | — | — | — | — |
| `STRIP_NULL_VALUE` | S | S | S | S | S | S | S | S | S | S | S |
| `STRLEN` | × | — | — | — | — | — | — | — | — | — | — |
| `STRPOS` | B | S | S | S | S | S | S | S | S | S | S |
| `STRPTIME` | S | — | — | — | — | — | — | — | — | — | — |
| `STRTOK` | S | S | S | S | S | S | S | S | S | S | S |
| `STRTOK_SPLIT_TO_TABLE` | S | S | S | S | S | S | S | S | S | S | S |
| `STRTOK_TO_ARRAY` | S | S | S | S | S | S | S | S | S | S | S |
| `STRTOL` | — | — | — | — | — | — | — | — | S | — | — |
| `STRUCT` | S | S | S | S | S | S | S | S | S | S | S |
| `STRUCT_CONCAT` | × | — | — | — | — | — | — | — | — | — | — |
| `STRUCT_CONTAINS` | × | — | — | — | — | — | — | — | — | — | — |
| `STRUCT_EXTRACT` | S | S | S | S | S | S | S | S | S | S | S |
| `STRUCT_EXTRACT_AT` | × | — | — | — | — | — | — | — | — | — | — |
| `STRUCT_INSERT` | × | — | — | — | — | — | — | — | — | — | — |
| `STRUCT_KEYS` | × | — | — | — | — | — | — | — | — | — | — |
| `STRUCT_PACK` | S | — | — | — | — | — | — | — | — | — | — |
| `STRUCT_POSITION` | × | — | — | — | — | — | — | — | — | — | — |
| `STRUCT_UPDATE` | × | — | — | — | — | — | — | — | — | — | — |
| `STRUCT_VALUES` | × | — | — | — | — | — | — | — | — | — | — |
| `STR_POSITION` | B | S | S | S | S | S | S | S | S | S | S |
| `STR_SPLIT` | S | — | — | — | — | — | — | — | — | — | — |
| `STR_SPLIT_REGEX` | S | — | — | — | — | — | — | — | — | — | — |
| `STR_TO_DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `STR_TO_MAP` | S | S | S | S | S | S | S | S | S | S | S |
| `STR_TO_TIME` | S | S | S | S | S | S | S | S | S | S | S |
| `STR_TO_UNIX` | S | S | S | S | S | S | S | S | S | S | S |
| `STUFF` | S | S | S | S | S | S | S | S | S | S | S |
| `ST_ADDPOINT` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_ANGLE` | — | — | — | × | — | — | — | — | × | — | — |
| `ST_AREA` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_ASBINARY` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_ASEWKB` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_ASEWKT` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_ASGEOJSON` | — | — | × | × | — | — | — | × | × | — | — |
| `ST_ASHEXEWKB` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_ASHEXWKB` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_ASTEXT` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_ASWKB` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_ASWKT` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_AZIMUTH` | — | — | × | × | — | — | — | × | × | — | — |
| `ST_BOUNDARY` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_BOUNDINGBOX` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_BUFFER` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_BUFFERWITHTOLERANCE` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_CENTROID` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_CENTROID_AGG` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_CLOSESTPOINT` | — | — | — | × | — | — | — | × | — | — | — |
| `ST_CLUSTERDBSCAN` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_COLLECT` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_CONCAVEHULL` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_CONTAINS` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_CONTAINSPROPERLY` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_CONVEXHULL` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_COORDDIM` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_COVEREDBY` | — | — | × | × | — | — | — | — | × | — | — |
| `ST_COVERS` | — | — | × | × | — | — | — | × | × | — | — |
| `ST_CROSSES` | — | — | — | — | — | — | — | — | × | × | — |
| `ST_DIFFERENCE` | — | — | × | × | — | — | — | × | — | × | — |
| `ST_DIMENSION` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_DISJOINT` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_DISTANCE` | S | S | S | S | S | S | S | S | S | S | S |
| `ST_DISTANCESPHERE` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_DISTANCESPHEROID` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_DUMP` | — | — | — | × | — | — | — | × | — | — | — |
| `ST_DWITHIN` | — | — | × | × | — | — | — | × | × | — | — |
| `ST_ENDPOINT` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_ENVELOPE` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_ENVELOPEASPTS` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_ENVELOPE_AGG` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_EQUALS` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_ESTIMATESRID` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_EXTENT` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_EXTERIORRING` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_FLIPCOORDINATES` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_FORCE2D` | — | — | — | — | — | — | — | × | × | × | — |
| `ST_FORCE3D` | — | — | — | — | — | — | — | — | × | × | — |
| `ST_FORCE3DM` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_FORCE3DZ` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_FORCE4D` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_GEOGFROM` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_GEOGFROMEWKT` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_GEOGFROMGEOHASH` | — | — | × | — | — | — | — | — | — | — | — |
| `ST_GEOGFROMGEOJSON` | — | — | — | × | — | — | — | × | — | — | — |
| `ST_GEOGFROMTEXT` | — | — | — | × | — | — | — | × | × | — | — |
| `ST_GEOGFROMWKB` | — | — | — | × | — | — | — | × | × | — | — |
| `ST_GEOGFROMWKT` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_GEOGPOINT` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_GEOGPOINTFROMGEOHASH` | — | — | × | × | — | — | — | — | — | — | — |
| `ST_GEOGRAPHYFROMWKB` | — | — | × | — | — | — | — | — | — | — | — |
| `ST_GEOGRAPHYFROMWKT` | — | — | × | — | — | — | — | — | — | — | — |
| `ST_GEOHASH` | — | — | × | × | — | — | — | × | × | — | — |
| `ST_GEOMETRIES` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_GEOMETRYFROMTEXT` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_GEOMETRYFROMWKB` | — | — | × | — | — | — | — | — | — | — | — |
| `ST_GEOMETRYFROMWKT` | — | — | × | — | — | — | — | — | — | — | — |
| `ST_GEOMETRYN` | — | — | — | — | — | — | — | × | × | × | — |
| `ST_GEOMETRYTYPE` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_GEOMFROMBINARY` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_GEOMFROMEWKB` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_GEOMFROMEWKT` | — | — | — | — | — | — | — | × | × | × | — |
| `ST_GEOMFROMGEOHASH` | — | — | × | — | — | — | — | × | × | — | — |
| `ST_GEOMFROMGEOJSON` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_GEOMFROMGEOSQUARE` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_GEOMFROMKML` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_GEOMFROMTEXT` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_GEOMFROMWKB` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_GEOMFROMWKT` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_GEOMPOINTFROMGEOHASH` | — | — | × | — | — | — | — | — | — | — | — |
| `ST_GEOSQUARE` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_HAUSDORFFDISTANCE` | — | — | × | × | — | — | — | — | — | — | — |
| `ST_HAUSDORFFDWITHIN` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_INTERIORRINGN` | — | — | — | — | — | — | — | × | × | × | — |
| `ST_INTERIORRINGS` | — | — | — | × | — | — | — | — | — | × | — |
| `ST_INTERPOLATE` | — | — | × | — | — | — | — | — | — | — | — |
| `ST_INTERSECTION` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_INTERSECTION_AGG` | — | — | × | — | — | — | — | — | — | — | — |
| `ST_INTERSECTS` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_INTERSECTSBOX` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_ISCLOSED` | — | — | — | × | — | — | — | — | × | × | — |
| `ST_ISCOLLECTION` | — | — | — | × | — | — | — | — | × | — | — |
| `ST_ISEMPTY` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_ISPOLYGONCCW` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_ISPOLYGONCW` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_ISRING` | — | — | — | × | — | — | — | — | × | × | — |
| `ST_ISSIMPLE` | — | — | — | — | — | — | — | — | × | × | — |
| `ST_ISVALID` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_LENGTH` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_LENGTH2D` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_LENGTHSPHERE` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_LINEFROMMULTIPOINT` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_LINEFROMTEXT` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_LINEINTERPOLATEPOINT` | — | — | — | × | — | — | — | — | × | — | — |
| `ST_LINELOCATEPOINT` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_LINEMERGE` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_LINESTRING` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_LINESUBSTRING` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_M` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_MAKEENVELOPE` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_MAKELINE` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_MAKEPOINT` | S | S | S | S | S | S | S | S | S | S | S |
| `ST_MAKEPOLYGON` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_MAKEPOLYGONORIENTED` | — | — | × | × | — | — | — | — | — | — | — |
| `ST_MAXDISTANCE` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_MEMSIZE` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_MINIMUMBOUNDINGCIRCLE` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_MMAX` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_MMIN` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_MULTI` | — | — | — | — | — | — | — | × | × | × | — |
| `ST_MULTIPOINT` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_NDIMS` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_NORMALIZE` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_NPOINTS` | — | — | — | × | — | — | — | × | × | — | — |
| `ST_NRINGS` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_NUMGEOMETRIES` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_NUMINTERIORRING` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_NUMINTERIORRINGS` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_NUMPOINTS` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_ORIENTEDENVELOPE` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_OVERLAPS` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_PERIMETER` | — | — | × | × | — | — | — | × | × | — | — |
| `ST_PERIMETER2D` | — | — | — | — | — | — | — | — | × | — | — |
| `ST_POINT` | S | S | S | S | S | S | S | S | S | S | S |
| `ST_POINTFROMGEOHASH` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_POINTN` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_POINTONSURFACE` | — | — | — | — | — | — | — | × | — | × | — |
| `ST_POINTS` | — | — | — | — | — | — | — | — | × | × | — |
| `ST_POLYGON` | — | — | — | — | — | — | — | — | × | × | — |
| `ST_POLYGONIZE` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_REDUCEPRECISION` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_REGIONSTATS` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_RELATE` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_REMOVEPOINT` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_REVERSE` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_ROTATE` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_SCALE` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_SETPOINT` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_SETSRID` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_SIMPLIFY` | — | — | × | × | — | — | — | × | × | — | — |
| `ST_SNAPTOGRID` | — | — | — | × | — | — | — | — | — | — | — |
| `ST_SRID` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_STARTPOINT` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_SYMDIFFERENCE` | — | — | × | — | — | — | — | — | — | × | — |
| `ST_TOUCHES` | — | — | — | × | — | — | — | × | × | × | — |
| `ST_TRANSFORM` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_TRANSLATE` | — | — | — | — | — | — | — | × | — | — | — |
| `ST_UNION` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_UNION_AGG` | — | — | × | × | — | — | — | × | — | — | — |
| `ST_VORONOIPOLYGONS` | — | — | — | — | — | — | — | — | — | × | — |
| `ST_WITHIN` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_X` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_XMAX` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_XMIN` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_Y` | — | — | × | × | — | — | — | × | × | × | — |
| `ST_YMAX` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_YMIN` | — | — | × | — | — | — | — | × | × | × | — |
| `ST_Z` | — | — | — | — | — | — | — | × | × | × | — |
| `ST_ZMAX` | — | — | — | — | — | — | — | × | × | — | — |
| `ST_ZMIN` | — | — | — | — | — | — | — | × | × | — | — |
| `SUBARRAY` | — | — | — | — | — | — | — | — | E | — | — |
| `SUBSTR` | S | S | S | S | S | S | S | S | S | S | S |
| `SUBSTRING` | S | S | S | S | S | S | S | S | S | S | S |
| `SUBSTRING_GRAPHEME` | × | — | — | — | — | — | — | — | — | — | — |
| `SUBSTRING_INDEX` | S | S | S | S | S | S | S | S | S | S | S |
| `SUBTRACT` | × | — | — | — | — | — | — | — | — | — | — |
| `SUFFIX` | × | — | — | — | — | — | — | — | — | — | — |
| `SUM` | B | B | S | S | B | B | B | B | B | S | S |
| `SUPPRESS_REDUNDANT_UPDATES_TRIGGER` | — | × | — | — | — | — | — | — | — | — | — |
| `SUSER_ID` | — | — | — | — | — | E | — | — | — | — | — |
| `SUSER_NAME` | — | — | — | — | — | S | S | — | — | — | — |
| `SUSER_SID` | — | — | — | — | — | E | × | — | — | — | — |
| `SUSER_SNAME` | — | — | — | — | — | S | S | — | — | — | — |
| `SWITCH` | × | × | — | — | — | — | — | — | — | — | — |
| `SWITCHOFFSET` | — | — | — | — | — | × | × | — | — | — | — |
| `SYMKEYPROPERTY` | — | — | — | — | — | × | — | — | — | — | — |
| `SYSDATE` | — | — | S | — | — | — | — | — | S | — | — |
| `SYSDATETIME` | — | — | — | — | — | S | S | — | — | — | — |
| `SYSDATETIMEOFFSET` | — | — | — | — | — | S | S | — | — | — | — |
| `SYSTEM$ABORT_SESSION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ABORT_TRANSACTION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ACTIVATE_CMK_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ACTIVATE_CMK_INFO_POSTGRES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ACTIVATE_CMK_INFO_SNOWFLAKE_MANAGED_VOLUME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ADD_PRIVATELINK_ENDPOINT_HOSTNAME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ADD_REFERENCE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ALLOWLIST` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ALLOWLIST_PRIVATELINK` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$APPLICATION_GET_LOG_LEVEL` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$APPLICATION_GET_METRIC_LEVEL` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$APPLICATION_GET_TRACE_LEVEL` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$APP_COMPATIBILITY_CHECK` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$AUTHORIZE_PRIVATELINK` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$AUTHORIZE_SNOWFLAKE_MANAGED_STORAGE_VOLUME_PRIVATELINK_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$AUTHORIZE_STAGE_PRIVATELINK_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$AUTO_REFRESH_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$BEGIN_DEBUG_APPLICATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$BEHAVIOR_CHANGE_BUNDLE_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$BLOCK_INTERNAL_STAGES_PUBLIC_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$BLOCK_INTERNAL_STAGES_PUBLIC_ACCESS_WITH_EXCEPTION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$BLOCK_SNOWFLAKE_MANAGED_STORAGE_VOLUME_PUBLIC_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$BLOCK_SNOWFLAKE_MANAGED_STORAGE_VOLUME_PUBLIC_ACCESS_WITH_EXCEPTION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CANCEL_ALL_QUERIES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CANCEL_QUERY` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CAST_MULTI_PARTY_APPROVAL_VOTE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CATALOG_LINK_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CKE_HASH_FUNCTION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CLEANUP_DATABASE_ROLE_GRANTS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CLIENT_VERSION_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CLIENT_VULNERABILITY_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CLUSTERING_DEPTH` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CLUSTERING_INFORMATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$COMMIT_MOVE_ORGANIZATION_ACCOUNT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CONVERT_PIPES_SQS_TO_SNS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CREATE_BILLING_EVENT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CREATE_BILLING_EVENTS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CREATE_EVALUATION_DATASET` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$CURRENT_USER_TASK_NAME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DATA_METRIC_SCAN` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DBT_GET_LAST_FAILED_RUN_TARGET` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DBT_GET_LAST_RUN_TARGET` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DBT_GET_LAST_SUCCESSFUL_RUN_TARGET` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DEACTIVATE_CMK_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DEACTIVATE_CMK_INFO_SNOWFLAKE_MANAGED_VOLUME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DECODE_PAT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DEMIGRATE_DBT_PROJECT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DEPROVISION_PRIVATELINK_ENDPOINT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DEPROVISION_PRIVATELINK_ENDPOINT_TSS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DEREGISTER_CMK_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DEREGISTER_CMK_INFO_POSTGRES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DEREGISTER_CMK_INFO_SNOWFLAKE_MANAGED_VOLUME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DESC_ICEBERG_ACCESS_IDENTITY` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DISABLE_BEHAVIOR_CHANGE_BUNDLE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DISABLE_DATABASE_REPLICATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DISABLE_FEATURE_GROUPS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DISABLE_FEATURE_GROUPS_PREVIEW` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DISABLE_GLOBAL_DATA_SHARING_FOR_ACCOUNT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DISABLE_PREVIEW_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$DISABLE_PRIVATELINK_ACCESS_ONLY` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ENABLE_BEHAVIOR_CHANGE_BUNDLE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ENABLE_FEATURE_GROUPS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ENABLE_GLOBAL_DATA_SHARING_FOR_ACCOUNT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ENABLE_PREVIEW_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ENCODE_CKE_PRIMARY_KEY` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$END_DEBUG_APPLICATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ENFORCE_PRIVATELINK_ACCESS_ONLY` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_COSTS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ESTIMATE_QUERY_ACCELERATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ESTIMATE_SEARCH_OPTIMIZATION_COSTS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$EVALUATE_DATA_QUALITY_EXPECTATIONS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$EVALUATE_DATA_QUALITY_EXPECTATIONS_PERSIST_RESULT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$EXECUTE_CATALOG_OPERATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$EXPLAIN_JSON_TO_TEXT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$EXPLAIN_PLAN_JSON` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$EXPORT_TDS_FROM_SEMANTIC_VIEW` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$EXTERNAL_TABLE_PIPE_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$FETCH_EXTERNAL_SECRET_FROM_INTEGRATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$FINISH_OAUTH_FLOW` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GENERATE_SAML_CSR` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GENERATE_SCIM_ACCESS_TOKEN` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_ALERT_CONFIG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_ALERT_TEMPLATE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_ALL_DEFAULT_COLUMNS_OVERRIDES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_ALL_REFERENCES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_APPLICATION_SERVICE_LOGS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_AWS_SNS_IAM_POLICY` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_CATALOG_LINKED_DATABASE_CONFIG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_CLASSIFICATION_RESULT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_CMK_AKV_CONSENT_URL` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_CMK_CONFIG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_CMK_CONFIG_POSTGRES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_CMK_CONFIG_SNOWFLAKE_MANAGED_VOLUME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_CMK_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_CMK_INFO_POSTGRES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_CMK_INFO_SNOWFLAKE_MANAGED_VOLUME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_CMK_KMS_KEY_POLICY` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_COMPUTE_POOL_PENDING_MAINTENANCE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_DBT_LOG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_DEBUG_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_DEFAULT_COLUMNS_OVERRIDE_FOR_SHOW_COMMAND` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_DEFAULT_COLUMNS_OVERRIDE_FOR_SYSTEM_OBJECT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_DIRECTORY_TABLE_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_GCP_KMS_CMK_GRANT_ACCESS_CMD` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_HASH_FOR_APPLICATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_ICEBERG_TABLE_INFORMATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_INSTANCE_FAMILY_PLACEMENT_GROUPS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_LISTING_URL_FOR_EXTERNAL_CONSUMER` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_LOGIN_FAILURE_DETAILS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_PREDECESSOR_RETURN_VALUE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_PREVIEW_ACCESS_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_PRIVATELINK` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_PRIVATELINK_AUTHORIZED_ENDPOINTS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_PRIVATELINK_CONFIG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_PRIVATELINK_ENDPOINT_REGISTRATIONS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_PURCHASE_ATTRIBUTES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_REFERENCED_OBJECT_ID_HASH` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_RESULTSET_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_SECURITY_INTEGRATIONS_FOR_API_PROVIDER` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_SERVICE_CALLER_TOKEN_EXPIRY` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_SERVICE_DNS_DOMAIN` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_SERVICE_LOGS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_SNOWFLAKE_EGRESS_IP_RANGES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_SNOWFLAKE_PLATFORM_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_STAGE_PRIVATELINK_AUTHORIZED_ENDPOINTS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_TABLE_ARCHIVE_METADATA` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_TAG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_TAG_ALLOWED_VALUES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_TAG_ON_CURRENT_COLUMN` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_TAG_ON_CURRENT_TABLE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_TASK_GRAPH_CONFIG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GET_TZDB_VERSION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$HOLD_PRIVILEGE_ON_ACCOUNT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$INGEST_REBIND_PIPE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$INITIATE_MOVE_ORGANIZATION_ACCOUNT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$INTERNAL_STAGES_PUBLIC_ACCESS_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ISSUE_PER_ACCOUNT_APP_SERVICE_CERTIFICATE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ISSUE_PER_ACCOUNT_CERTIFICATES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$IS_APPLICATION_ALL_MANDATORY_TELEMETRY_EVENT_DEFINITIONS_ENABLED` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$IS_APPLICATION_AUTHORIZED_FOR_TELEMETRY_EVENT_SHARING` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$IS_APPLICATION_INSTALLED_FROM_SAME_ACCOUNT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$IS_APPLICATION_SHARING_EVENTS_WITH_PROVIDER` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$IS_GLOBAL_DATA_SHARING_ENABLED_FOR_ACCOUNT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$IS_LISTING_PURCHASED` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$IS_LISTING_TRIAL` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LAST_CHANGE_COMMIT_TIME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LINK_ACCOUNT_OBJECTS_BY_NAME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LINK_ORGANIZATION_USER` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LINK_ORGANIZATION_USER_GROUP` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LIST_ALERT_TEMPLATES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LIST_APPLICATION_RESTRICTED_FEATURES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LIST_EXTERNAL_SECRETS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LIST_NAMESPACES_FROM_CATALOG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LOCATE_DBT_ARCHIVE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$LOCATE_DBT_ARTIFACTS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$MIGRATE_DBT_PROJECT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$MIGRATE_LEGACY_EVENT_ROUTING_CONFIGURATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$MIGRATE_SAML_IDP_REGISTRATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$OPT_IN_INTERNAL_STAGE_NETWORK_LOGS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$OPT_OUT_INTERNAL_STAGE_NETWORK_LOGS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$OPT_OUT_MALICIOUS_IP_PROTECTION_BY_CATEGORY` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$PARQUET_DIRECT_AUTO_REFRESH_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$PIPE_FORCE_RESUME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$PIPE_REBINDING_WITH_NOTIFICATION_CHANNEL` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$PIPE_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$PREDECESSORS_STATE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT_TSS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$QUERY_REFERENCE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$READ_OSI_YAML_FROM_SEMANTIC_VIEW` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$READ_OSSIE_YAML_FROM_SEMANTIC_VIEW` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REFERENCE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REGISTER_CMK_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REGISTER_CMK_INFO_POSTGRES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REGISTER_CMK_INFO_SNOWFLAKE_MANAGED_VOLUME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REGISTER_PRIVATELINK_ENDPOINT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REMOTE_APP_OPERATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REMOVE_ALL_REFERENCES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REMOVE_PRIVATELINK_ENDPOINT_HOSTNAME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REMOVE_REFERENCE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REPORT_HEALTH_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$RESOLVE_PYTHON_PACKAGES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$RESTORE_PRIVATELINK_ENDPOINT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$RESTORE_PRIVATELINK_ENDPOINT_TSS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REVOKE_PRIVATELINK` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REVOKE_SNOWFLAKE_MANAGED_STORAGE_VOLUME_PRIVATELINK_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$REVOKE_STAGE_PRIVATELINK_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SCHEDULE_ASYNC_REPLICATION_GROUP_REFRESH` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SEND_NOTIFICATIONS_TO_CATALOG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SET_APPLICATION_RESTRICTED_FEATURE_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SET_CATALOG_INTEGRATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SET_DEFAULT_COLUMNS_OVERRIDE_FOR_SHOW_COMMAND` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SET_DEFAULT_COLUMNS_OVERRIDE_FOR_SYSTEM_OBJECT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SET_REFERENCE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SET_RETURN_VALUE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SET_ROW_TIMESTAMP_ON_ALL_SUPPORTED_TABLES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SHOW_ACTIVE_BEHAVIOR_CHANGE_BUNDLES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SHOW_BUDGETS_FOR_RESOURCE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SHOW_BUDGETS_IN_ACCOUNT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SHOW_DYNAMIC_TABLES_CREATED_FOR_RESHARING` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SHOW_EVENT_SHARING_ACCOUNTS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SHOW_MOVE_ORGANIZATION_ACCOUNT_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SHOW_OAUTH_CLIENT_SECRETS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SNOWFLAKE_MANAGED_STORAGE_VOLUME_PUBLIC_ACCESS_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SNOWPIPE_STREAMING_UPDATE_CHANNEL_OFFSET_TOKEN` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$START_OAUTH_FLOW` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$START_USER_EMAIL_VERIFICATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$STREAM_BACKLOG` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$STREAM_GET_TABLE_TIMESTAMP` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$STREAM_HAS_DATA` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$SUPPORTED_DBT_VERSIONS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$TAG_VALUE_CONTAINS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$TAG_VALUE_CONTAINS_ON_CURRENT_COLUMN` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$TAG_VALUE_CONTAINS_ON_CURRENT_TABLE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$TASK_COMPLETION_STATE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$TASK_DEPENDENTS_ENABLE` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$TASK_RUNTIME_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$TRIGGER_LISTING_REFRESH` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$TYPEOF` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNBLOCK_INTERNAL_STAGES_PUBLIC_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNBLOCK_SNOWFLAKE_MANAGED_STORAGE_VOLUME_PUBLIC_ACCESS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNLINK_ORGANIZATION_USER` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNLINK_ORGANIZATION_USER_GROUP` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNMANAGE_ENTITY_FROM_DCM_PROJECT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNMANAGE_FROM_DCM_PROJECT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNREGISTER_PRIVATELINK_ENDPOINT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNSET_DEFAULT_COLUMNS_OVERRIDE_FOR_SHOW_COMMAND` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNSET_DEFAULT_COLUMNS_OVERRIDE_FOR_SYSTEM_OBJECT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNSET_EVENT_SHARING_ACCOUNT_FOR_REGION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UNVERIFY_DNS_DOMAIN` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$UPDATE_MULTI_PARTY_APPROVAL_JUSTIFICATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$USER_TASK_CANCEL_ONGOING_EXECUTIONS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$VALIDATE_STORAGE_INTEGRATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$VERIFY_CATALOG_INTEGRATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$VERIFY_CMK_INFO` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$VERIFY_CMK_INFO_POSTGRES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$VERIFY_CMK_INFO_SNOWFLAKE_MANAGED_VOLUME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$VERIFY_DNS_DOMAIN` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$VERIFY_EXTERNAL_OAUTH_TOKEN` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$VERIFY_EXTERNAL_SECRET_INTEGRATION` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$VERIFY_EXTERNAL_VOLUME` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$WAIT` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$WAIT_FOR_OPENFLOW_CONNECTOR_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$WAIT_FOR_OPENFLOW_DEPLOYMENT_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$WAIT_FOR_OPENFLOW_RUNTIME_STATUS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$WAIT_FOR_SERVICES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$WAIT_FOR_STABLE_OPENFLOW_CONNECTORS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$WAIT_FOR_STABLE_OPENFLOW_DEPLOYMENTS` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM$WAIT_FOR_STABLE_OPENFLOW_RUNTIMES` | — | — | × | — | — | — | — | — | — | — | — |
| `SYSTEM_USER` | — | × | — | — | — | S | S | — | — | — | — |
| `SYSTIMESTAMP` | S | S | S | S | S | S | S | S | S | S | S |
| `SYSUTCDATETIME` | — | — | — | — | — | × | × | — | — | — | — |
| `SYS_CONTEXT` | — | — | × | — | — | — | — | — | — | — | — |
| `S_H_A1_DIGEST` | S | S | S | S | S | S | S | S | S | S | S |
| `S_H_A2_DIGEST` | S | S | S | S | S | S | S | S | S | S | S |
| `TABLE` | — | — | S | — | — | — | — | — | — | — | — |
| `TABLE_CHANGES` | — | — | — | — | — | — | — | × | — | — | — |
| `TABLE_TO_XML` | — | × | — | — | — | — | — | — | — | — | — |
| `TABLE_TO_XMLSCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `TABLE_TO_XML_AND_XMLSCHEMA` | — | × | — | — | — | — | — | — | — | — | — |
| `TAG_REFERENCES` | — | — | × | — | — | — | — | — | — | — | — |
| `TAG_REFERENCES_ALL_COLUMNS` | — | — | × | — | — | — | — | — | — | — | — |
| `TAG_REFERENCES_WITH_LINEAGE` | — | — | × | — | — | — | — | — | — | — | — |
| `TAN` | S | S | S | S | S | S | S | S | S | S | S |
| `TAND` | — | × | — | — | — | — | — | — | — | — | — |
| `TANH` | S | S | S | S | S | S | S | S | S | S | S |
| `TASK_DEPENDENTS` | — | — | × | — | — | — | — | — | — | — | — |
| `TASK_GRAPH_CHANGES` | — | — | × | — | — | — | — | — | — | — | — |
| `TASK_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `TDIGEST_AGG` | — | — | — | — | — | — | — | — | — | × | × |
| `TEXT` | — | × | — | — | — | — | — | — | — | — | — |
| `TEXTLEN` | — | — | — | — | — | — | — | — | S | — | — |
| `TEXT_ANALYZE` | — | — | — | × | — | — | — | — | — | — | — |
| `TEXT_HTML` | — | — | × | — | — | — | — | — | — | — | — |
| `TEXT_PLAIN` | — | — | × | — | — | — | — | — | — | — | — |
| `TEXT_TO_INT_ALT` | — | — | — | — | — | — | — | — | × | — | — |
| `TEXT_TO_NUMERIC_ALT` | — | — | — | — | — | — | — | — | × | — | — |
| `TF_IDF` | — | — | — | × | — | — | — | — | — | — | — |
| `THETA_DIFFERENCE` | — | — | — | — | — | — | — | × | — | — | — |
| `THETA_INTERSECTION` | — | — | — | — | — | — | — | × | — | — | — |
| `THETA_INTERSECTION_AGG` | — | — | — | — | — | — | — | × | — | — | — |
| `THETA_SKETCH_AGG` | — | — | — | — | — | — | — | × | — | — | — |
| `THETA_SKETCH_CARDINALITY` | — | — | — | — | — | — | — | — | — | × | — |
| `THETA_SKETCH_ESTIMATE` | — | — | — | — | — | — | — | × | — | — | — |
| `THETA_SKETCH_UNION` | — | — | — | — | — | — | — | — | — | × | — |
| `THETA_UNION` | — | — | — | — | — | — | — | × | — | — | — |
| `THETA_UNION_AGG` | — | — | — | — | — | — | — | × | — | — | — |
| `TIME` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMEADD` | — | — | S | — | — | — | — | — | — | — | — |
| `TIMEDIFF` | — | — | S | — | — | — | — | × | — | — | — |
| `TIMEFROMPARTS` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMEOFDAY` | — | E | — | — | — | — | — | — | × | — | — |
| `TIMESTAMP` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMPADD` | — | — | S | — | S | — | — | S | — | — | — |
| `TIMESTAMPDIFF` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMPFROMPARTS` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMPLTZFROMPARTS` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMPNTZFROMPARTS` | — | — | S | — | — | — | — | — | — | — | — |
| `TIMESTAMPTZFROMPARTS` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMPTZ_CMP` | — | — | — | — | — | — | — | — | × | — | — |
| `TIMESTAMPTZ_CMP_DATE` | — | — | — | — | — | — | — | — | × | — | — |
| `TIMESTAMPTZ_CMP_TIMESTAMP` | — | — | — | — | — | — | — | — | × | — | — |
| `TIMESTAMP_ADD` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMP_BUCKET` | — | — | — | E | — | — | — | — | — | — | — |
| `TIMESTAMP_CMP` | — | — | — | — | — | — | — | — | × | — | — |
| `TIMESTAMP_CMP_DATE` | — | — | — | — | — | — | — | — | × | — | — |
| `TIMESTAMP_CMP_TIMESTAMPTZ` | — | — | — | — | — | — | — | — | × | — | — |
| `TIMESTAMP_DIFF` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMP_FROM_PARTS` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMP_LTZ` | — | — | — | — | S | — | — | S | — | — | — |
| `TIMESTAMP_LTZ_FROM_PARTS` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMP_MICROS` | — | — | — | S | E | — | — | E | — | — | — |
| `TIMESTAMP_MILLIS` | — | — | — | S | E | — | — | E | — | — | — |
| `TIMESTAMP_NANOS` | — | — | — | — | — | — | — | × | — | — | — |
| `TIMESTAMP_NTZ` | — | — | — | — | S | — | — | S | — | — | — |
| `TIMESTAMP_NTZ_FROM_PARTS` | — | — | S | — | — | — | — | — | — | — | — |
| `TIMESTAMP_OBJECTID` | — | — | — | — | — | — | — | — | — | × | — |
| `TIMESTAMP_SECONDS` | — | — | — | S | E | — | — | E | — | — | — |
| `TIMESTAMP_SUB` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMP_TRUNC` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMESTAMP_TZ_FROM_PARTS` | S | S | S | S | S | S | S | S | S | S | S |
| `TIMETZ_BYTE_COMPARABLE` | × | — | — | — | — | — | — | — | — | — | — |
| `TIMEZONE` | × | × | — | — | — | — | — | — | × | × | × |
| `TIMEZONE_HOUR` | × | — | — | — | — | — | — | — | — | × | × |
| `TIMEZONE_MINUTE` | × | — | — | — | — | — | — | — | — | × | × |
| `TIME_ADD` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_BUCKET` | S | — | — | — | — | — | — | × | — | — | — |
| `TIME_DIFF` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_FROM_MICROS` | — | — | — | — | — | — | — | × | — | — | — |
| `TIME_FROM_MILLIS` | — | — | — | — | — | — | — | × | — | — | — |
| `TIME_FROM_PARTS` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_FROM_SECONDS` | — | — | — | — | — | — | — | × | — | — | — |
| `TIME_SLICE` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_STR_TO_DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_STR_TO_TIME` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_STR_TO_UNIX` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_SUB` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_TO_MICROS` | — | — | — | — | — | — | — | × | — | — | — |
| `TIME_TO_MILLIS` | — | — | — | — | — | — | — | × | — | — | — |
| `TIME_TO_SECONDS` | — | — | — | — | — | — | — | × | — | — | — |
| `TIME_TO_STR` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_TO_TIME_STR` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_TO_UNIX` | S | S | S | S | S | S | S | S | S | S | S |
| `TIME_TRUNC` | S | S | S | S | S | S | S | S | S | S | S |
| `TINYINT` | — | — | — | — | E | — | — | E | — | — | — |
| `TITLE_CASE` | — | — | — | — | — | — | — | — | — | × | × |
| `TODATETIMEOFFSET` | — | — | — | — | — | × | × | — | — | — | — |
| `TODAY` | S | — | — | — | — | — | — | — | — | — | — |
| `TO_ARRAY` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_ASCII` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_AVRO` | — | — | — | — | — | — | — | × | — | — | — |
| `TO_BASE` | × | — | — | — | — | — | — | — | — | × | × |
| `TO_BASE32` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_BASE64` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_BASE64URL` | — | — | — | — | — | — | — | — | — | × | × |
| `TO_BIG_ENDIAN_32` | — | — | — | — | — | — | — | — | — | × | × |
| `TO_BIG_ENDIAN_64` | — | — | — | — | — | — | — | — | — | × | × |
| `TO_BIN` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_BINARY` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_BOOLEAN` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_CENTURIES` | × | — | — | — | — | — | — | — | — | — | — |
| `TO_CHAR` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_CODE_POINTS` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_CSV` | — | — | — | — | E | — | — | E | — | — | — |
| `TO_DATE` | — | S | S | — | S | — | — | S | S | × | × |
| `TO_DAYS` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_DECADES` | × | — | — | — | — | — | — | — | — | — | — |
| `TO_DECFLOAT` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_DECIMAL` | — | — | S | — | — | — | — | — | — | — | — |
| `TO_DOUBLE` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_ENCODED_POLYLINE` | — | — | — | — | — | — | — | — | — | × | × |
| `TO_FILE` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_GEOGRAPHY` | — | — | S | — | — | — | — | × | — | — | — |
| `TO_GEOJSON_GEOMETRY` | — | — | — | — | — | — | — | — | — | — | × |
| `TO_GEOMETRY` | — | — | S | — | — | — | — | × | — | × | × |
| `TO_HEX` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_HOURS` | × | — | — | — | — | — | — | — | — | — | — |
| `TO_IEEE754_32` | — | — | — | — | — | — | — | — | — | × | × |
| `TO_IEEE754_64` | — | — | — | — | — | — | — | — | — | × | × |
| `TO_IPADDRESS` | — | — | × | — | — | — | — | — | — | — | — |
| `TO_ISO8601` | — | — | — | — | — | — | — | — | — | E | E |
| `TO_JSON` | — | × | S | S | S | — | — | S | — | — | — |
| `TO_JSONB` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_JSON_STRING` | — | — | — | S | — | — | — | — | — | — | — |
| `TO_MAP` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_MICROSECONDS` | × | — | — | — | — | — | — | — | — | — | — |
| `TO_MILLENNIA` | × | — | — | — | — | — | — | — | — | — | — |
| `TO_MILLISECONDS` | × | — | — | — | — | — | — | — | — | × | × |
| `TO_MINUTES` | × | — | — | — | — | — | — | — | — | — | — |
| `TO_MONTHS` | × | — | — | — | — | — | — | — | — | — | — |
| `TO_NUMBER` | S | S | B | S | S | S | S | S | S | S | S |
| `TO_NUMERIC` | — | — | S | — | — | — | — | — | — | — | — |
| `TO_OBJECT` | — | — | × | — | — | — | — | — | — | — | — |
| `TO_OCT` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_PROTOBUF` | — | — | — | — | — | — | — | × | — | — | — |
| `TO_QUARTERS` | × | — | — | — | — | — | — | — | — | — | — |
| `TO_QUERY` | — | — | × | — | — | — | — | — | — | — | — |
| `TO_REGCLASS` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_REGCOLLATION` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_REGNAMESPACE` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_REGOPER` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_REGOPERATOR` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_REGPROC` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_REGPROCEDURE` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_REGROLE` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_REGTYPE` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_REGTYPEMOD` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_SECONDS` | × | — | — | — | — | — | — | — | — | — | — |
| `TO_SPHERICAL_GEOGRAPHY` | — | — | — | — | — | — | — | — | — | × | × |
| `TO_TIME` | — | — | S | — | — | — | — | × | — | — | — |
| `TO_TIMESTAMP` | B | S | S | — | S | — | — | S | S | × | × |
| `TO_TIMESTAMP_LTZ` | — | — | S | — | E | — | — | E | — | — | — |
| `TO_TIMESTAMP_NTZ` | — | — | S | — | E | — | — | E | — | — | — |
| `TO_TIMESTAMP_TZ` | — | — | S | — | — | — | — | — | — | — | — |
| `TO_TSQUERY` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_TSVECTOR` | — | × | — | — | — | — | — | — | — | — | — |
| `TO_UNIXTIME` | — | — | — | — | — | — | — | — | — | S | S |
| `TO_UNIX_TIMESTAMP` | — | — | — | — | S | — | — | S | — | — | — |
| `TO_UTC_TIMESTAMP` | — | — | — | — | S | — | — | S | — | — | — |
| `TO_UTF8` | — | — | — | — | — | — | — | — | — | S | S |
| `TO_UUID` | — | — | × | — | — | — | — | — | — | — | — |
| `TO_VARBYTE` | — | — | — | — | — | — | — | — | × | — | — |
| `TO_VARCHAR` | — | — | S | — | E | — | — | E | — | — | — |
| `TO_VARIANT` | S | S | S | S | S | S | S | S | S | S | S |
| `TO_VARIANT_OBJECT` | — | — | — | — | — | — | — | E | — | — | — |
| `TO_WEEKS` | × | — | — | — | — | — | — | — | — | — | — |
| `TO_XML` | — | — | × | — | — | — | — | E | — | — | — |
| `TO_YEARS` | × | — | — | — | — | — | — | — | — | — | — |
| `TRANSACTION_TIMESTAMP` | × | E | — | — | — | — | — | — | — | — | — |
| `TRANSFORM` | S | S | S | S | S | S | S | S | S | S | S |
| `TRANSFORM_KEYS` | — | — | — | — | × | — | — | × | — | × | × |
| `TRANSFORM_VALUES` | — | — | — | — | × | — | — | × | — | × | × |
| `TRANSLATE` | S | S | S | S | S | S | S | S | S | S | S |
| `TRIGGER_NESTLEVEL` | — | — | — | — | — | × | — | — | — | — | — |
| `TRIM` | S | S | S | S | S | S | S | S | S | S | S |
| `TRIM_ARRAY` | — | × | — | — | — | — | — | — | — | × | × |
| `TRIM_SCALE` | — | × | — | — | — | — | — | — | — | — | — |
| `TRUNC` | S | S | S | S | S | S | S | S | S | S | S |
| `TRUNCATE` | S | S | S | S | S | S | S | S | S | S | S |
| `TRY` | S | S | S | S | S | S | S | S | S | S | S |
| `TRY_ADD` | — | — | — | — | S | — | — | S | — | — | — |
| `TRY_AES_DECRYPT` | — | — | — | — | E | — | — | E | — | — | — |
| `TRY_AVG` | — | — | — | — | E | — | — | E | — | — | — |
| `TRY_BASE64_DECODE_BINARY` | S | S | S | S | S | S | S | S | S | S | S |
| `TRY_BASE64_DECODE_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `TRY_CAST` | S | S | S | S | S | S | S | S | S | S | S |
| `TRY_CONVERT` | S | S | S | S | S | S | S | S | S | S | S |
| `TRY_COPY_FILE` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_DECRYPT` | — | — | S | — | — | — | — | — | — | — | — |
| `TRY_DECRYPT_RAW` | — | — | S | — | — | — | — | — | — | — | — |
| `TRY_DIVIDE` | — | — | — | — | S | — | — | S | — | — | — |
| `TRY_ELEMENT_AT` | — | — | — | — | S | — | — | S | — | — | — |
| `TRY_HEX_DECODE_BINARY` | S | S | S | S | S | S | S | S | S | S | S |
| `TRY_HEX_DECODE_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `TRY_IP_AS_BINARY` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_IP_AS_STRING` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_IP_CIDR` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_IP_HOST` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_MAKE_INTERVAL` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_MAKE_TIMESTAMP` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_MAKE_TIMESTAMP_LTZ` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_MAKE_TIMESTAMP_NTZ` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_MOD` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_MULTIPLY` | — | — | — | — | S | — | — | S | — | — | — |
| `TRY_PARSE` | — | — | — | — | — | × | × | — | — | — | — |
| `TRY_PARSE_JSON` | — | — | S | — | — | — | — | E | — | — | — |
| `TRY_PARSE_TIMESTAMP` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_REFLECT` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_SECRET` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_STRPTIME` | × | — | — | — | — | — | — | — | — | — | — |
| `TRY_SUBTRACT` | — | — | — | — | S | — | — | S | — | — | — |
| `TRY_SUM` | — | — | — | — | E | — | — | E | — | — | — |
| `TRY_TO_BINARY` | — | — | S | — | E | — | — | E | — | — | — |
| `TRY_TO_BOOLEAN` | — | — | S | — | — | — | — | — | — | — | — |
| `TRY_TO_DATE` | — | — | S | — | — | — | — | × | — | — | — |
| `TRY_TO_DECFLOAT` | S | S | S | S | S | S | S | S | S | S | S |
| `TRY_TO_DECIMAL` | — | — | S | — | — | — | — | — | — | — | — |
| `TRY_TO_DOUBLE` | — | — | S | — | — | — | — | — | — | — | — |
| `TRY_TO_FILE` | — | — | S | — | — | — | — | × | — | — | — |
| `TRY_TO_GEOGRAPHY` | — | — | × | — | — | — | — | × | — | — | — |
| `TRY_TO_GEOMETRY` | — | — | × | — | — | — | — | × | — | — | — |
| `TRY_TO_IPADDRESS` | — | — | × | — | — | — | — | — | — | — | — |
| `TRY_TO_NUMBER` | — | — | S | — | E | — | — | E | — | — | — |
| `TRY_TO_NUMERIC` | — | — | S | — | — | — | — | — | — | — | — |
| `TRY_TO_TIME` | — | — | S | — | — | — | — | × | — | — | — |
| `TRY_TO_TIMESTAMP` | — | — | S | — | E | — | — | E | — | — | — |
| `TRY_TO_TIMESTAMP_LTZ` | — | — | S | — | — | — | — | — | — | — | — |
| `TRY_TO_TIMESTAMP_NTZ` | — | — | S | — | — | — | — | — | — | — | — |
| `TRY_TO_TIMESTAMP_TZ` | — | — | S | — | — | — | — | — | — | — | — |
| `TRY_TO_UUID` | — | — | × | — | — | — | — | — | — | — | — |
| `TRY_URL_DECODE` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_VALIDATE_UTF8` | — | — | — | — | — | — | — | × | — | — | — |
| `TRY_VARIANT_GET` | — | — | — | — | — | — | — | E | — | — | — |
| `TRY_ZSTD_DECOMPRESS` | — | — | — | — | — | — | — | × | — | — | — |
| `TSQUERY_PHRASE` | — | × | — | — | — | — | — | — | — | — | — |
| `TSVECTOR_TO_ARRAY` | — | × | — | — | — | — | — | — | — | — | — |
| `TSVECTOR_UPDATE_TRIGGER` | — | × | — | — | — | — | — | — | — | — | — |
| `TSVECTOR_UPDATE_TRIGGER_COLUMN` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_DEBUG` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_DELETE` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_FILTER` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_HEADLINE` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_LEXIZE` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_OR_DI_TO_DI` | S | S | S | S | S | S | S | S | S | S | S |
| `TS_OR_DS_ADD` | S | S | S | S | S | S | S | S | S | S | S |
| `TS_OR_DS_DIFF` | S | S | S | S | S | S | S | S | S | S | S |
| `TS_OR_DS_TO_DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `TS_OR_DS_TO_DATETIME` | S | S | S | S | S | S | S | S | S | S | S |
| `TS_OR_DS_TO_DATE_STR` | S | S | S | S | S | S | S | S | S | S | S |
| `TS_OR_DS_TO_TIME` | S | S | S | S | S | S | S | S | S | S | S |
| `TS_OR_DS_TO_TIMESTAMP` | S | S | S | S | S | S | S | S | S | S | S |
| `TS_PARSE` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_RANK` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_RANK_CD` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_REWRITE` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_STAT` | — | × | — | — | — | — | — | — | — | — | — |
| `TS_TOKEN_TYPE` | — | × | — | — | — | — | — | — | — | — | — |
| `TUPLE_DIFFERENCE_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_DIFFERENCE_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_DIFFERENCE_THETA_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_DIFFERENCE_THETA_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_INTERSECTION_AGG_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_INTERSECTION_AGG_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_INTERSECTION_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_INTERSECTION_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_INTERSECTION_THETA_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_INTERSECTION_THETA_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_SKETCH_AGG_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_SKETCH_AGG_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_SKETCH_ESTIMATE_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_SKETCH_ESTIMATE_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_SKETCH_SUMMARY_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_SKETCH_SUMMARY_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_SKETCH_THETA_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_SKETCH_THETA_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_UNION_AGG_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_UNION_AGG_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_UNION_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_UNION_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_UNION_THETA_DOUBLE` | — | — | — | — | — | — | — | × | — | — | — |
| `TUPLE_UNION_THETA_INTEGER` | — | — | — | — | — | — | — | × | — | — | — |
| `TXID_CURRENT` | E | E | — | — | — | — | — | — | — | — | — |
| `TXID_CURRENT_IF_ASSIGNED` | — | × | — | — | — | — | — | — | — | — | — |
| `TXID_CURRENT_SNAPSHOT` | — | × | — | — | — | — | — | — | — | — | — |
| `TXID_SNAPSHOT_XIP` | — | × | — | — | — | — | — | — | — | — | — |
| `TXID_SNAPSHOT_XMAX` | — | × | — | — | — | — | — | — | — | — | — |
| `TXID_SNAPSHOT_XMIN` | — | × | — | — | — | — | — | — | — | — | — |
| `TXID_STATUS` | — | × | — | — | — | — | — | — | — | — | — |
| `TXID_VISIBLE_IN_SNAPSHOT` | — | × | — | — | — | — | — | — | — | — | — |
| `TYPEOF` | S | S | S | S | S | S | S | S | S | S | S |
| `TYPEPROPERTY` | — | — | — | — | — | E | × | — | — | — | — |
| `TYPE_ID` | — | — | — | — | — | E | × | — | — | — | — |
| `TYPE_NAME` | — | — | — | — | — | E | × | — | — | — | — |
| `T_CDF` | — | — | — | — | — | — | — | — | — | — | × |
| `T_PDF` | — | — | — | — | — | — | — | — | — | — | × |
| `UCASE` | S | S | S | S | S | S | S | S | S | S | S |
| `UNBASE64` | — | — | — | — | S | — | — | S | — | — | — |
| `UNBIN` | × | — | — | — | — | — | — | — | — | — | — |
| `UNHEX` | S | S | S | S | S | S | S | S | S | S | S |
| `UNICODE` | S | S | S | S | S | S | S | S | S | S | S |
| `UNICODE_ASSIGNED` | — | × | — | — | — | — | — | — | — | — | — |
| `UNICODE_VERSION` | — | × | — | — | — | — | — | — | — | — | — |
| `UNIFORM` | S | S | S | S | S | S | S | S | S | S | S |
| `UNION_EXTRACT` | × | — | — | — | — | — | — | — | — | — | — |
| `UNION_TAG` | × | — | — | — | — | — | — | — | — | — | — |
| `UNION_VALUE` | × | — | — | — | — | — | — | — | — | — | — |
| `UNISTR` | — | × | — | — | — | × | × | — | — | — | — |
| `UNIX_DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `UNIX_MICROS` | S | S | S | S | S | S | S | S | S | S | S |
| `UNIX_MILLIS` | S | S | S | S | S | S | S | S | S | S | S |
| `UNIX_NANOS` | — | — | — | — | — | — | — | × | — | — | — |
| `UNIX_SECONDS` | S | S | S | S | S | S | S | S | S | S | S |
| `UNIX_TIMESTAMP` | — | — | — | — | S | — | — | S | — | — | — |
| `UNIX_TO_STR` | S | S | S | S | S | S | S | S | S | S | S |
| `UNIX_TO_TIME` | B | S | S | S | S | S | S | S | S | S | S |
| `UNIX_TO_TIME_STR` | S | S | S | S | S | S | S | S | S | S | S |
| `UNNEST` | S | S | S | S | S | S | S | S | S | S | S |
| `UNPIVOT_LIST` | × | — | — | — | — | — | — | — | — | — | — |
| `UPPER` | S | S | S | S | S | S | S | S | S | S | S |
| `UPPER_ATTRIBUTE_NAMES` | — | — | — | — | — | — | — | — | × | — | — |
| `UPPER_INC` | — | × | — | — | — | — | — | — | — | — | — |
| `UPPER_INF` | — | × | — | — | — | — | — | — | — | — | — |
| `URL_DECODE` | × | — | — | — | × | — | — | × | — | × | × |
| `URL_ENCODE` | × | — | — | — | × | — | — | × | — | × | × |
| `URL_EXTRACT_FRAGMENT` | — | — | — | — | — | — | — | — | — | × | × |
| `URL_EXTRACT_HOST` | — | — | — | — | — | — | — | — | — | × | × |
| `URL_EXTRACT_PARAMETER` | — | — | — | — | — | — | — | — | — | × | × |
| `URL_EXTRACT_PATH` | — | — | — | — | — | — | — | — | — | × | × |
| `URL_EXTRACT_PORT` | — | — | — | — | — | — | — | — | — | × | × |
| `URL_EXTRACT_PROTOCOL` | — | — | — | — | — | — | — | — | — | × | × |
| `URL_EXTRACT_QUERY` | — | — | — | — | — | — | — | — | — | × | × |
| `USER` | — | × | — | — | E | × | — | E | S | — | — |
| `USER_ID` | — | — | — | — | — | E | — | — | — | — | — |
| `USER_IS_MEMBER_OF` | — | — | — | — | — | — | — | — | × | — | — |
| `USER_NAME` | — | — | — | — | — | E | × | — | — | — | — |
| `UTC_DATE` | S | S | S | S | S | S | S | S | S | S | S |
| `UTC_TIME` | S | S | S | S | S | S | S | S | S | S | S |
| `UTC_TIMESTAMP` | S | S | S | S | S | S | S | S | S | S | S |
| `UUID` | S | S | S | S | S | S | S | S | S | S | S |
| `UUIDV4` | × | × | — | — | — | — | — | — | — | — | — |
| `UUIDV7` | × | E | — | — | — | — | — | — | — | — | — |
| `UUID_EXTRACT_TIMESTAMP` | × | × | — | — | — | — | — | — | — | — | — |
| `UUID_EXTRACT_VERSION` | × | × | — | — | — | — | — | — | — | — | — |
| `UUID_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `VALIDATE` | — | — | × | — | — | — | — | — | — | — | — |
| `VALIDATE_PIPE_LOAD` | — | — | × | — | — | — | — | — | — | — | — |
| `VALIDATE_UTF8` | — | — | — | — | — | — | — | × | — | — | — |
| `VALUES_AT_QUANTILES` | — | — | — | — | — | — | — | — | — | × | × |
| `VALUE_AT_QUANTILE` | — | — | — | — | — | — | — | — | — | × | × |
| `VAR` | — | — | — | — | — | × | × | — | — | — | — |
| `VARIANCE` | S | B | S | S | S | S | S | S | S | S | S |
| `VARIANCE_POP` | S | B | S | S | S | S | S | S | S | S | S |
| `VARIANCE_SAMP` | S | B | S | S | S | S | S | S | S | S | S |
| `VARIANT_ARRAY_LENGTH` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_COMPARATOR` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_CONTAINS` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_EXISTS` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_EXPLODE` | — | — | — | — | — | — | — | E | — | — | — |
| `VARIANT_EXPLODE_OUTER` | — | — | — | — | — | — | — | E | — | — | — |
| `VARIANT_EXTRACT` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_EXTRACT_STRING` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_GET` | — | — | — | — | — | — | — | E | — | — | — |
| `VARIANT_GROUP_ARRAY` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_GROUP_OBJECT` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_KEYS` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_NORMALIZE` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_TYPE` | × | — | — | — | — | — | — | — | — | — | — |
| `VARIANT_TYPEOF` | × | — | — | — | — | — | — | — | — | — | — |
| `VARP` | — | — | — | — | — | × | × | — | — | — | — |
| `VAR_MAP` | S | S | S | S | S | S | S | S | S | S | S |
| `VAR_POP` | S | B | S | S | S | S | S | S | S | S | S |
| `VAR_SAMP` | S | B | S | S | S | S | S | S | S | S | S |
| `VECTORPROPERTY` | — | — | — | — | — | × | — | — | — | — | — |
| `VECTOR_AVG` | — | — | × | — | — | — | — | × | — | — | — |
| `VECTOR_COSINE_SIMILARITY` | — | — | S | — | — | — | — | × | — | — | — |
| `VECTOR_DISTANCE` | — | — | — | — | — | × | — | — | — | — | — |
| `VECTOR_INDEX.STATISTICS` | — | — | — | × | — | — | — | — | — | — | — |
| `VECTOR_INNER_PRODUCT` | — | — | S | — | — | — | — | × | — | — | — |
| `VECTOR_L1_DISTANCE` | — | — | S | — | — | — | — | — | — | — | — |
| `VECTOR_L2_DISTANCE` | — | — | S | — | — | — | — | × | — | — | — |
| `VECTOR_MAX` | — | — | × | — | — | — | — | — | — | — | — |
| `VECTOR_MIN` | — | — | × | — | — | — | — | — | — | — | — |
| `VECTOR_NORM` | — | — | — | — | — | × | — | × | — | — | — |
| `VECTOR_NORMALIZE` | — | — | × | — | — | × | — | × | — | — | — |
| `VECTOR_SEARCH` | S | S | S | S | S | S | S | S | S | S | S |
| `VECTOR_SUM` | — | — | × | — | — | — | — | × | — | — | — |
| `VECTOR_TRUNCATE` | — | — | × | — | — | — | — | — | — | — | — |
| `VERIFYSIGNEDBYASYMKEY` | — | — | — | — | — | × | — | — | — | — | — |
| `VERIFYSIGNEDBYCERT` | — | — | — | — | — | × | — | — | — | — | — |
| `VERSION` | S | S | — | — | E | — | — | E | S | S | S |
| `WAREHOUSE_LOAD_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `WAREHOUSE_METERING_HISTORY` | — | — | × | — | — | — | — | — | — | — | — |
| `WEBSEARCH_TO_TSQUERY` | — | × | — | — | — | — | — | — | — | — | — |
| `WEEK` | S | S | S | S | S | S | S | S | S | S | S |
| `WEEKDAY` | × | — | — | — | E | — | — | E | — | — | — |
| `WEEKISO` | — | — | S | — | — | — | — | — | — | — | — |
| `WEEKOFYEAR` | B | S | S | S | S | S | S | S | S | S | S |
| `WEEK_OF_YEAR` | B | S | S | S | S | S | S | S | S | S | S |
| `WEEK_START` | S | S | S | S | S | S | S | S | S | S | S |
| `WEIGHTED_AVG` | × | — | — | — | — | — | — | — | — | — | — |
| `WEIGHT_STRING` | S | S | S | S | S | S | S | S | S | S | S |
| `WIDTH` | — | × | — | — | — | — | — | — | — | — | — |
| `WIDTH_BUCKET` | S | S | S | S | S | S | S | S | S | S | S |
| `WILSON_INTERVAL_LOWER` | — | — | — | — | — | — | — | — | — | × | × |
| `WILSON_INTERVAL_UPPER` | — | — | — | — | — | — | — | — | — | × | × |
| `WINDOW` | — | — | — | — | E | — | — | E | — | — | — |
| `WINDOW_TIME` | — | — | — | — | E | — | — | E | — | — | — |
| `WITH_TIMEZONE` | — | — | — | — | — | — | — | — | — | × | × |
| `WORD_STEM` | — | — | — | — | — | — | — | — | — | × | × |
| `XACT_STATE` | — | — | — | — | — | E | — | — | — | — | — |
| `XMLAGG` | — | × | — | — | — | — | — | — | — | — | — |
| `XMLCOMMENT` | — | × | — | — | — | — | — | — | — | — | — |
| `XMLCONCAT` | — | × | — | — | — | — | — | — | — | — | — |
| `XMLELEMENT` | S | S | S | S | S | S | S | S | S | S | S |
| `XMLEXISTS` | — | × | — | — | — | — | — | — | — | — | — |
| `XMLFOREST` | — | × | — | — | — | — | — | — | — | — | — |
| `XMLGET` | S | S | S | S | S | S | S | S | S | S | S |
| `XMLPARSE` | — | × | — | — | — | — | — | — | — | — | — |
| `XMLPI` | — | × | — | — | — | — | — | — | — | — | — |
| `XMLROOT` | — | × | — | — | — | — | — | — | — | — | — |
| `XMLSERIALIZE` | — | × | — | — | — | — | — | — | — | — | — |
| `XMLTABLE` | S | S | S | S | S | S | S | S | S | S | S |
| `XMLTEXT` | — | × | — | — | — | — | — | — | — | — | — |
| `XML_IS_WELL_FORMED` | — | × | — | — | — | — | — | — | — | — | — |
| `XML_IS_WELL_FORMED_CONTENT` | — | × | — | — | — | — | — | — | — | — | — |
| `XML_IS_WELL_FORMED_DOCUMENT` | — | × | — | — | — | — | — | — | — | — | — |
| `XOR` | S | S | S | S | S | S | S | S | S | S | S |
| `XPATH` | — | × | — | — | × | — | — | × | — | — | — |
| `XPATH_BOOLEAN` | — | — | — | — | × | — | — | × | — | — | — |
| `XPATH_DOUBLE` | — | — | — | — | × | — | — | × | — | — | — |
| `XPATH_EXISTS` | — | × | — | — | — | — | — | — | — | — | — |
| `XPATH_FLOAT` | — | — | — | — | × | — | — | × | — | — | — |
| `XPATH_INT` | — | — | — | — | × | — | — | × | — | — | — |
| `XPATH_LONG` | — | — | — | — | × | — | — | × | — | — | — |
| `XPATH_NUMBER` | — | — | — | — | × | — | — | × | — | — | — |
| `XPATH_SHORT` | — | — | — | — | × | — | — | × | — | — | — |
| `XPATH_STRING` | — | — | — | — | × | — | — | × | — | — | — |
| `XXHASH64` | — | — | — | — | × | — | — | × | — | × | × |
| `X_M_L_TABLE` | S | S | S | S | S | S | S | S | S | S | S |
| `YEAR` | S | S | S | S | S | S | S | S | S | S | S |
| `YEAROFWEEK` | S | S | S | S | S | S | S | S | S | S | S |
| `YEAROFWEEKISO` | S | S | S | S | S | S | S | S | S | S | S |
| `YEARWEEK` | × | — | — | — | — | — | — | — | — | — | — |
| `YEAR_OF_WEEK` | S | S | S | S | S | S | S | S | S | S | S |
| `YEAR_OF_WEEK_ISO` | S | S | S | S | S | S | S | S | S | S | S |
| `YOW` | — | — | — | — | — | — | — | — | — | × | × |
| `ZEROIFNULL` | — | — | S | — | — | — | — | × | — | — | — |
| `ZIP` | — | — | — | — | — | — | — | — | — | × | × |
| `ZIPF` | S | S | S | S | S | S | S | S | S | S | S |
| `ZIP_WITH` | — | — | — | — | × | — | — | × | — | E | × |
| `ZSTD_COMPRESS` | — | — | — | — | — | — | — | × | — | — | — |
| `ZSTD_DECOMPRESS` | — | — | — | — | — | — | — | × | — | — | — |
| `_1` | — | — | — | — | × | — | — | — | — | — | — |
| `_10` | — | — | — | — | × | — | — | — | — | — | — |
| `_11` | — | — | — | — | × | — | — | — | — | — | — |
| `_12` | — | — | — | — | × | — | — | — | — | — | — |
| `_13` | — | — | — | — | × | — | — | — | — | — | — |
| `_14` | — | — | — | — | × | — | — | — | — | — | — |
| `_15` | — | — | — | — | × | — | — | — | — | — | — |
| `_16` | — | — | — | — | × | — | — | — | — | — | — |
| `_17` | — | — | — | — | × | — | — | — | — | — | — |
| `_18` | — | — | — | — | × | — | — | — | — | — | — |
| `_19` | — | — | — | — | × | — | — | — | — | — | — |
| `_2` | — | — | — | — | × | — | — | — | — | — | — |
| `_3` | — | — | — | — | × | — | — | — | — | — | — |
| `_4` | — | — | — | — | × | — | — | — | — | — | — |
| `_5` | — | — | — | — | × | — | — | — | — | — | — |
| `_6` | — | — | — | — | × | — | — | — | — | — | — |
| `_7` | — | — | — | — | × | — | — | — | — | — | — |
| `_8` | — | — | — | — | × | — | — | — | — | — | — |
| `_9` | — | — | — | — | × | — | — | — | — | — | — |
<!-- END GENERATED FUNCTION INVENTORY -->
