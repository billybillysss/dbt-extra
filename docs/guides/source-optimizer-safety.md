# Authored-SQL optimizer safety

The source optimizer validates bindings before its general structural rules and
again afterward, including after rendering. Two narrow, explicit-binding input
normalizations (positive equality-EXISTS and complementary UNION ALL scans) run
before qualification; unsupported shapes are not normalized. It uses SQLGlot scopes and
schemas, not textual alias replacement. This protects renamed CTE outputs and
avoids guessing which joined relation owns an unqualified column.

## Schema evidence

`optimize_source(code, dialect, *, schema=None, pretty=True, outcomes=None)` accepts complete,
ordered relation schemas as dictionaries or native SQLGlot schemas. Dictionary
column identifiers retain their authored case and quoting through star expansion.
Supplying a schema asserts completeness; a partial list of documentation columns
is not a valid caller schema.

Project optimization recursively infers supported local model output interfaces
from the operation's authored SQL/macro snapshot. Evidence records resource
identity, ordered identifiers, completeness, provenance, and snapshot freshness.
Inference caches are operation-local and dependency cycles are explicit skips.
This describes query definitions, not a promise about stored warehouse relations.

YAML properties and manifest/catalog column documentation are **not exhaustive
schema evidence**. Catalogs are not trusted for source star expansion without a
verifiable freshness contract. No warehouse, adapter, dbt, Fabric, or environment
access is performed. Unknown joined schemas cannot establish the absence of a
column; ambiguous unqualified columns and unknown-schema USING/NATURAL joins
disable binding-dependent transformations, not safe local literal work.

Projection stars require complete ordered schemas. Supported EXCLUDE/EXCEPT and
REPLACE forms are qualified and expanded. Star RENAME, ILIKE, other unsupported
modifiers, and duplicate outputs retain their interface rather than guessing bindings.
`COUNT(*)` is an aggregate, not a projection star requiring expansion.

## Rewrite boundaries

The eligible structural sequence is:

```text
guarded positive WHERE EXISTS / complementary UNION ALL normalization
→ qualify / expand stars
→ scope-aware dead projection pruning
→ local type-guarded expression simplification
→ scope-local guarded Boolean normalization / predicate pushdown
→ eligible subquery merging / inner-join simplification
→ guarded deterministic shared-subquery factoring
→ eligible unused-CTE cleanup
→ requalify / validate
→ generated alias naming / redundant alias cleanup
→ render / reparse / revalidate
```

Eligibility for expression movement is conservative and specific to a candidate region. Aggregates
(including empty-input global aggregates), outer joins, windows, positional
ordering, DISTINCT, limits/offsets, set operations, HAVING, QUALIFY, and correlation
restrict movement across those boundaries. A rejected parent region does not
prevent safe work in an independent child/sibling region. Independent rules have
their own guards; identical grouped derived tables can be factored without
flattening aggregation. Boolean
normalization is bounded; OR join predicates are not split into separate joins.
Shared CTE consumers and native scope dependencies
are retained. Source optimization does not eliminate joins or infer uniqueness.

Local expression work has separate eligibility: aggregates, windows, outer joins,
set operations and limits do not prevent folding a safe `1 + 2` projection or
removing `WHERE TRUE` in place. These rules do not move expressions between scopes.
They preserve comments and skip GROUP/ORDER expressions, where replacing an
expression with an integer could introduce an ordinal column reference. Boolean
identity removal requires a proven Boolean expression, not a coerced numeric,
string, or opaque macro operand.

Arithmetic is not simplified just because values look equivalent. Small integer
literal addition/subtraction/multiplication folds only within the nonnegative
signed-32-bit range in fixed-width-integer literal dialects (DuckDB, PostgreSQL,
Spark, T-SQL and BigQuery). Snowflake literal precision is not assumed equivalent.
Decimal arithmetic, division, overflowing constants and unproven coercions stay
authored. Predicate rules that internally invoke unrestricted simplification are
guarded against arithmetic, casts, functions and mixed-type constant comparisons.

Only a direct input column declared INT or BIGINT in DuckDB currently admits
`column + 0 → column`. Other dialects/types and computed or unknown input types
are not inferred safe. In particular, `DECIMAL(12,2) + 0` can return
`DECIMAL(13,2)`, and folding `1.00 + 2.00` can shrink decimal precision. Project
schema evidence proves output names, not exact warehouse types; documentation
types do not authorize these rewrites. This is a narrow rule allowlist, not general
warehouse type inference or a runtime proof of output-type equivalence.

Only a positive conjunctive WHERE `EXISTS(SELECT 1 FROM one_table WHERE
inner.key = outer.key AND inner_only_filters)` is decorrelated to membership.
All columns must be explicitly qualified. It does not apply to SELECT truth
values, NOT, OR, multiple correlation keys, aggregates, limits, joins, or nested
subqueries. Both keys must be base-table columns with the same explicitly declared
TINYINT, SMALLINT, INT or BIGINT type, currently only in DuckDB and Spark. Unknown,
mixed, string, decimal and derived-column types retain EXISTS: equality and IN
can have different coercion/binding rules. Project interface evidence proves names,
not physical key types, so it does not authorize this rewrite. Other correlated
shapes retain their boundaries. Duplicates cannot multiply the
outer rows, and SQL FALSE/UNKNOWN both reject rows in this WHERE context.

Complementary UNION ALL scans collapse only when both plain branches have
identical column projections and inputs, differing solely in `column = literal`
versus `column <> literal`, with a non-NULL literal. The replacement retains both
comparisons with OR, excluding NULL keys, preserving duplicates and retaining
comparison coercions instead of assuming types to emit IS NOT NULL. DISTINCT, differing inputs/outputs,
joins, limits and other modifiers are not collapsed.

Authored relation, CTE, and output names remain authored. Only optimizer-generated
relation aliases become `a` through `z`, then `aa`, `ab`, etc., skipping occupied
identifiers deterministically. `a.col AS col` is removed only when the identifiers
match exactly, including case and quoting. Unnamed expression outputs are not
relabeled or passed through general structural rules, avoiding synthetic labels
that would change database results.

The optimizer requires a fixed point within four passes, rejecting cycles or
nonconvergence. Each eligible rule starts from a copy of the last validated state.
SQLGlot errors and explicit validation rejections roll back only that candidate;
qualified rules rebuild bindings after changes. Failed qualification disables
binding-dependent work. Unexpected programming exceptions are not recoverable
rule failures. The SQLGlot-integration `KeyError` wrapper produces a
chained actionable model error; unrelated parser/programming errors propagate.
Final comments, output interfaces, dbt calls and parse/render checks still apply.
These are structural checks, **not runtime-equivalence validation**: they do not
prove result rows, exact database types, error behavior or evaluation counts.
Optimized project models omit statement terminators so dbt can embed them in
materialization queries; standalone SQL output retains its terminator.

## Macros, preview, and conflicts

By default (`--expand false`), supported scalar macros are inspected through bounded static expansion. A separate,
narrow pruning rule uses expanded, qualified dependencies to remove dead authored
columns and proven-safe grouped aggregate outputs, including identifiers hidden in macro string
arguments. This pruning rule deletes projections only; a separate local expression
pass can simplify independent SQL constants and Boolean identities. Neither rule
moves, expands, duplicates, or removes an authored macro call, nor simplifies an
expression containing a macro placeholder. Scope/projection mapping for pruning
must remain one-to-one.
DISTINCT tuples, global aggregate cardinality, positional and ALL dependencies,
shared consumers, window dependencies, HAVING, filters, and limits are retained.
Potentially fallible outputs such as `SUM`, `MAX`, casts and unknown functions
are retained without a dialect/type proof of harmless removal. Native `COUNT`
and `ROW_NUMBER` removal is currently enabled only for the tested DuckDB/Spark
semantics; function recognition alone does not authorize deletion.
Other unsupported shapes remain formatting-only. Raw custom macro call text and counts
must survive. SQL-fragment macros skip in this default preservation mode.

`optimize --expand true` (or `optimization.expand: true`) explicitly replaces supported
local macro calls with SQL before applying the ordinary source rewrite rules.
This also supports static multiple-column and SQL-clause output, not just scalar
macros. Relation/config templates remain authored and upstream models are not
inlined. Unsupported calls skip the whole model unchanged; no partial expansion
is written. Expanded queries still pass binding, output-interface, comment,
render/reparse and fixed-point checks. Expansion is reported as a structural rewrite
even if no further SQL simplification occurs. Macro definition files are unchanged.

The static allowlist includes argument-free string `upper`, `lower`, and `strip`
methods and `upper`, `lower`, and `trim` filters, flat tuple-unpacking literal
loops, same-type string/numeric/Boolean comparisons, and Boolean short-circuiting.
Recursion, size, loop and work budgets limit expansion. Arbitrary Python/Jinja execution, adapter/context
calls, database queries, and environment access remain disallowed.

Literal top-level assignments, loops, nested static conditions and whitespace
controls are also analyzable with the same budgets. Default source optimization
retains the whole original template unchanged; explicit `--expand true` opts into
rendering reduced SQL. Runtime-dependent templates still skip rather than guess
their output shape. See [partial optimization](partial-optimization.md).

The ChangeSet watches snapshot bytes for upstream SQL, macros, configuration,
properties, and loaded or absent artifact paths, not just selected output files.
Apply rejects changes to watched inputs even when the SQL proposal is a no-op.
Preview writes nothing. CLI reporting separates structurally rewritten, qualified,
formatting-only, and byte-unchanged models, plus proposed SQL changes, skipped
models, and SQL files actually written. Classification compares the original SQL
with the final fixed point, not just the last optimizer pass. Formatting and
qualification alone are not reported as structural optimization or speedups.
Each model's report also includes `retained` explanations for remaining arithmetic
identities, DISTINCT tuples, and aggregate/window/row-limit movement boundaries.
The CLI prints these reasons in preview and apply modes; they are not failures
and do not imply that independent safe local rewrites were disabled.

## Dialect selection

Adapter autodetection maps `fabricspark` to SQLGlot `spark` and `sqlserver` to
`tsql`. Fabric Warehouse retains its dedicated `fabric` dialect, not `tsql`.
Explicit CLI and configuration dialect overrides retain priority. Parser support
does not grant dialect-specific arithmetic rewrite permissions; related dialects
stay excluded until their semantics are tested. See [dialect coverage](../compatibility.md#sql-dialects).

## Regression coverage

The [source optimizer tests](../../tests/sql/test_source_optimization.py) cover
AST bindings, DuckDB output labels, exact types (including decimal precision/scale)
and row multisets (including duplicates, NULLs, empty/unmatched inputs), overflow
and conversion-error retention, ordered results, eleven SQL dialects, macro
preservation, preview byte identity, conflicts, and idempotence. Write-mode tests
use temporary project copies.

The strict [execution oracle](../../tests/semantics.py) requires success unless a
specific error is expected, compares error reasons, and compares ordered rows
when the outer query promises order. Deliberately broken candidates check that
lost duplicates, NULLs, rows, ordering, labels and types are detected.
[Seeded cases](../../tests/sql/test_generated_optimization.py) vary data and query
constants, including asymmetric empty inputs and multi-rule interactions.
[Independent Jinja checks](../../tests/sql/test_jinja_execution.py) use real Jinja,
and the [dbt rebuild test](../../tests/workflows/test_optimizer_dbt_execution.py)
builds original and rewritten temporary projects with real dbt-duckdb.

See [compatibility](../compatibility.md#sql-dialects) for engine-specific coverage
and [testing](../development/testing.md) for commands. Regression
checks are **not a proof of general SQL equivalence, Fabric compatibility, or a
measured performance/cost improvement**.
