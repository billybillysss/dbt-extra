# SQL functions: local gap implementations and enrichment

SQL-function enrichment infers missing column data types from statically
analyzable expressions using SQLGlot and available schema evidence. Function
coverage varies by dialect and input types. Parsing support does not guarantee
type inference or safe optimization.

## Implemented dialect catalogs

| SQLGlot dialect | Local function gaps | Function catalog | Separate regression suite |
| --- | --- | --- | --- |
| `spark` | 86 | [Spark functions and types](spark.md) | [Spark tests](../../../tests/sql/functions/test_spark.py) |
| `tsql` | 76 | [T-SQL functions and types](tsql.md) | [T-SQL tests](../../../tests/sql/functions/test_tsql.py) |

These **162 distinct function names** fill demonstrated SQLGlot 30.29.0 gaps:
each example still parses as `exp.Anonymous` without dbt-extra. Native functions
such as `UPPER`, `SUM`, `EXPLODE`, `OPENJSON` and `JSON_VALUE` are not counted.
Each local entry is tested for recognition, shape, type inference, rewrite safety,
and YAML enrichment. Type-policy `unresolved / input-dependent` is intentional:
recognizing a scalar, aggregate or generator does not justify guessing its type.

Recognition preserves the original SQLGlot AST and function spelling, with a
dialect-local semantic lookup. It does not relabel every Anonymous expression as
scalar, modify SQLGlot globally, or authorize SQL-function evaluation. Scalar and
aggregate calls return one value; generators may emit multiple columns or change
row counts. `JSON_TUPLE` arity follows its key arguments; `STRING_SPLIT` has one
column by default and two with literal ordinal flag `1`. `INLINE_OUTER` can use
literal struct width; otherwise its column count remains unknown. Spark `WINDOW`
and `SESSION_WINDOW` are conservative expansion/session barriers, not movable scalars.

All local calls currently retain rewrite barriers, including deterministic calls
that may raise, environment-sensitive functions, reflection and `try_*` functions.
No folding, removal, duplication or movement permission follows from an inferred
type. Unknown names, schema-qualified/quoted calls, and unsupported argument counts
remain unknown. Generator queries cannot provide metadata types/lineage until
their output schema is established. No window-function gap is currently claimed.

The shared SQL regression matrix also covers DuckDB, PostgreSQL, Snowflake,
BigQuery, Fabric, Databricks, Redshift, Trino and Athena; those dialects have **no
local gap catalog**. SQLGlot-native inference is still available, but shared SQL
tests are not function-level or warehouse certification. Related dialects do not
inherit local catalogs implicitly.

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

These are SQLGlot-rendered type names, not complete warehouse function signatures.
For example, `VARCHAR` does not establish a string length. Precision, scale,
nullability, implicit conversions and runtime errors need independent review.
No Spark or SQL Server warehouse is executed by this matrix.

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
See the [enrichment workflow](../../guides/inspection-and-optimization.md#enrich-metadata).

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
