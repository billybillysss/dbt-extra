# Partial SQL optimization

dbt-extra optimizes only transformations with sufficient evidence. An unsupported
expression is not permission to guess its columns, type, cardinality or effects;
it is also not a reason to abandon independent literal simplification.

`inspect` renders expanded, optionally selected-column explanation SQL. Authored
`optimize` preserves output names/order, comments and dbt/Jinja calls. They share
safety analysis, but not their rendering contracts. Inspection is not proof that
inlining a stored model is equivalent to reading its materialized relation.

## Requirements and boundaries

| Transformation | Evidence and boundary |
| --- | --- |
| Literal simplification | Individual expression; dialect-approved integer range/type and no discarded fallible evaluation |
| Projection pruning | Qualified scope dependencies across every consumer, clause aliases, ordinals and set-operation positions |
| Predicate movement | Proven-safe source/destination region; no aggregate, window, row-limit, outer-join or correlation boundary crossing |
| Join reordering | Plain inner/cross region with safe predicates and evaluation |
| Join elimination (inspection only) | Unused LEFT-join RHS, SQL-derived uniqueness/singleton proof and safe evaluation; never column non-use alone |
| Expansion | Supported individual upstream resource, explicit boundaries and complete evidence for column demands |

Eligible child regions can be optimized even when their parent or sibling is
blocked. Aggregate detection for projection dependencies distinguishes the owning
SELECT from windows and scalar subqueries. Global aggregates retain an aggregate
witness, including on empty input. DISTINCT/set duplicate semantics, shared CTE
consumers, QUALIFY aliases and positional dependencies are retained. Projection
pruning never removes joins itself.

Join elimination retains filtered RHS queries and matching comparisons
without a same-column-origin type proof. Uniqueness alone does not justify
erasing an implicit conversion error in the filter or join condition.
Predicate rules also retain input-dependent comparisons when third-party
simplification would erase them without a type/totality proof, including an
otherwise absorbing `TRUE OR comparison` or `FALSE AND comparison`.

Function recognition is separate from safety. The proof model tracks knownness,
scalar/aggregate/window/generator kind, volatility, fallibility and output
shape/type. Unknown functions, casts, arithmetic and unproven aggregate effects
are retained rather than evaluated, duplicated, moved or discarded. The narrow
native COUNT/ROW_NUMBER discardability proofs currently apply to DuckDB and
Spark, not automatically to T-SQL or related dialects. Without the required proof,
SUM/MAX projections and joins are retained.

Local function definitions describe existing warehouse functions; they are not
executed UDF implementations or a way to bypass safety checks. Recognition can
provide type/shape/effect evidence, but does not itself authorize a rewrite.
Unused Spark/Databricks `isnull` and `isnotnull` outputs have a separate removal
proof only when their arguments are independently discardable; casts or unknown
calls inside the arguments prevent it. See [why dbt-extra defines SQL function
semantics](../reference/sql-functions/README.md#why-dbt-extra-defines-sql-function-semantics)
for before/after examples.

An unsupported function or rejected rule does not necessarily block independent
projection pruning, literal work or eligible regions. Partial optimization does
not require every function to be registered first. Some structural rules still
use whole-query guards, so this is not a promise that every barrier is local.

For example, both paths can fold `1 + 2` and remove `WHERE TRUE` here without
changing the unknown call:

```sql
SELECT 1 + 2 AS k, mystery(x) AS opaque FROM t WHERE TRUE;
```

They do not reduce `(2147483647 + 1) * 0` to a successful zero when the original
can overflow, or push a false outer predicate below a global aggregate.

## Checkpoints and reporting

Each eligible rule receives a candidate copy of the last validated tree.
Applicable parse/render, output/comment and binding validation runs before commit.
A recoverable SQLGlot error or explicit validation rejection discards only that
candidate. Earlier work survives; failed candidates never provide capabilities to
dependent rules. Structural edits invalidate analysis and rebuild bindings/scopes.
Qualification failure blocks binding-dependent rules, not local literal work.
Final whole-query output and round-trip checks still apply. Programming errors
are not caught indiscriminately; unrecoverable parse, dependency-cycle and
fixed-point failures retain the existing error contract.

Inspection issues carry `resource_id`, `reason` and transformation fields. Project
optimization includes an `outcomes` list in each model's report.
`optimize_source()` returns SQL and can populate an optional `outcomes` list; see
the [Python API](../reference/python-api.md#standalone-sql) for an example.

Each outcome contains:

| Field | Meaning |
| --- | --- |
| `rule` | Stable transformation name, such as `projection_pruning` |
| `resource_id` | dbt resource ID, or SQL context for standalone calls |
| `scope` | Query/resource or operation-local scope label; not a persistent AST ID |
| `status` | `applied`, `not_applicable`, `blocked`, or `rolled_back` |
| `reason_code` | Machine-readable explanation category |
| `reason` | Human-readable detail; do not parse this field as a protocol |
| `occurrence_count` | Number of identical outcomes combined in this operation |

The CLI renders non-`not_applicable` outcomes, including scope and repeated
occurrence counts.
An `applied` outcome describes an accepted checkpoint, not a warehouse performance
claim; later passes may find the same rule not applicable.

## Bounded top-level templates

Literal `{% set %}`, finite literal `{% for %}` and statically boolean
`{% if %}`/`elif`/`else` blocks can be analyzed without executing Jinja. Nested
loops, loop metadata, comments and whitespace control are supported. Literal dbt
`ref`, `source`, `config` and `this` calls survive reduction as dbt expressions.
Interpreter budgets remain bounded: 10,000 work units, 1,000 items per loop,
100,000 output characters and depth 20. Hygienic tokens cannot collide with SQL
or trigger recursive template evaluation.

No values are invented for `var`, `env_var`, `run_query` or `is_incremental()`.
An unresolved runtime template is a resource boundary. Its table can remain in
expanded inspection while independent supported resources are optimized; an
unparseable root cannot be assigned an invented output shape.

By default authored optimization preserves an entire top-level template exactly,
and reports that preservation boundary. It does not reverse-map edits into
loop-generated source spans. `optimize --expand true` explicitly permits static
template reduction to SQL while retaining dbt relation/config calls. Existing
scalar local macro calls remain authored unless expansion is explicitly enabled.

## Expansion reuse

Parsing, complete schema evidence, demand analysis and reusable expanded bodies
are cached per operation. Reliable selected-output demands propagate upstream;
row-affecting clauses and all consumers contribute dependencies. Unknown bindings
keep the original body. Documented YAML columns are **not** an exhaustive schema.
Explicit `--from` boundaries take precedence.

Repeated boundary messages are combined with occurrence counts. Cached SQL is
copied for each lexical occurrence: caching is not authorization to factor
volatile or correlated SQL into shared CTEs. Qualification can enlarge rendered
SQL even while pruning AST nodes. See [testing](../development/testing.md) for
benchmark commands, structural-growth checks and engine-specific execution lanes.
