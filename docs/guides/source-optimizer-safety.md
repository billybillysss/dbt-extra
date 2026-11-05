# Authored-SQL optimizer safety

The source optimizer validates bindings before its general structural rules and
again afterward, including after rendering. Two narrow, explicit-binding input
normalizations (positive equality-EXISTS and complementary UNION ALL scans) run
before qualification; unsupported shapes are not normalized. It uses SQLGlot scopes and
schemas, not textual alias replacement. This protects renamed CTE outputs and
avoids guessing which joined relation owns an unqualified column.

## Schema evidence

`optimize_source(code, dialect, *, schema=None, pretty=True)` accepts complete,
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
column; ambiguous unqualified columns and unknown-schema USING/NATURAL joins skip.

Projection stars require complete ordered schemas. Supported EXCLUDE/EXCEPT and
REPLACE forms are qualified and expanded. Star RENAME, ILIKE, other unsupported
modifiers, and duplicate outputs skip rather than silently change the interface.
`COUNT(*)` is an aggregate, not a projection star requiring expansion.

## Rewrite boundaries

The eligible structural sequence is:

```text
guarded positive WHERE EXISTS / complementary UNION ALL normalization
→ qualify / expand stars
→ scope-aware dead projection pruning
→ local type-guarded expression simplification
→ guarded projection pushdown
→ eligible predicate pushdown
→ eligible subquery merging
→ eliminate unused CTEs
→ guarded Boolean normalization / DISTINCT predicate pushdown / inner-join simplification
→ guarded deterministic shared-subquery factoring
→ requalify / validate
→ generated alias naming / redundant alias cleanup
→ render / reparse / revalidate
```

Eligibility for expression movement is intentionally query-wide and conservative. Aggregates
(including empty-input global aggregates), outer joins, windows, positional
ordering, DISTINCT, limits/offsets, set operations, HAVING, QUALIFY, and correlation
restrict expression movement. Independent rules have their own guards: ordinary
DISTINCT can admit predicate pushdown without changing its tuple, and identical
grouped derived tables can be factored without flattening aggregation. Boolean
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
subqueries. Other correlated shapes still skip. Duplicates cannot multiply the
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
nonconvergence. SQLGlot qualification/rule errors, including `KeyError`, become
chained, actionable per-model skips. Unrelated programming errors are not blanket
caught. Skipped models have no proposed SQL write; other selected models continue.

## Macros, preview, and conflicts

By default (`--expand false`), supported scalar macros are inspected through bounded static expansion. A separate,
narrow pruning rule uses expanded, qualified dependencies to remove dead authored
columns and grouped aggregates, including identifiers hidden in macro string
arguments. This pruning rule deletes projections only; a separate local expression
pass can simplify independent SQL constants and Boolean identities. Neither rule
moves, expands, duplicates, or removes an authored macro call, nor simplifies an
expression containing a macro placeholder. Scope/projection mapping for pruning
must remain one-to-one.
DISTINCT tuples, global aggregate cardinality, positional and ALL dependencies,
shared consumers, window dependencies, HAVING, filters, and limits are retained.
For example, the leaderboard can drop unused `largest_order` and
`returned_order_count` aggregates without changing its ranking or final limit.
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

The static allowlist includes argument-free string `upper`, `lower`, and `trim`
methods/filters, flat tuple-unpacking literal loops, same-type string/numeric/
boolean comparisons, and boolean short-circuiting. Existing recursion, size,
loop, and work budgets remain. Arbitrary Python/Jinja execution, adapter/context
calls, database queries, and environment access remain disallowed.

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
and conversion-error retention, ordered results, seven SQL dialects, macro
preservation, preview byte identity, conflicts, and idempotence. Write-mode tests
use temporary project copies.

See [testing](../development/testing.md) for portable test commands. Regression
checks are **not a proof of general SQL equivalence, Fabric compatibility, or a
measured performance/cost improvement**.
