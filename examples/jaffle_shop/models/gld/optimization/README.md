# Optimizer demonstrations

These 14 executable dbt models each demonstrate an authored-SQL rewrite, not just
pretty-printing. Applying optimization changes these files, so a local copy may
already be optimized. Canonical before-inputs live in
[the test fixtures](../../../../../tests/fixtures/optimization); regression tests
seed those inputs in disposable project copies and require all 14 to rewrite.
Run the commands below from the repository root. No warehouse, dbt compilation,
manifest, or catalog is needed by dbt-extra. See the [project README](../../../README.md)
for a separate, optional `dbt build` using the supplied seeds.

## Two different operations

- **`optimize` edits authored SQL**, but only after validating bindings, output
  names/order, Jinja calls, comments, SQL round-tripping, and convergence to a
  fixed point. Use `--preview` here; apply only to a disposable project copy.
- **`inspect` is read-only**. It can expand local model definitions, expand known
  scalar macros for analysis, select outputs, and perform more structural rewrites.
  `--compile false` keeps `ref`/`source` calls visible. Relation compilation is not
  dbt compilation. `--view plan` shows a logical plan, not a warehouse execution plan.

```bash
extra --project-dir examples/jaffle_shop optimize --select 'path:models/gld/optimization/**' --preview
extra --project-dir examples/jaffle_shop inspect gld_optimizer_projections --expand false --compile false --optimize false
extra --project-dir examples/jaffle_shop inspect gld_optimizer_projections --expand false --compile false --optimize true
```

From the canonical inputs, all 14 models receive substantive source rewrites.
The report distinguishes structurally rewritten, qualified, formatting-only and
unchanged models. A second run on the optimized files is unchanged; an accepted
model or text diff alone is not evidence of optimization. For example, omitting
DuckDB's default `NULLS LAST` is not a rewrite. Preview writes no SQL files.

## Rule-to-demo matrix

Names below omit the `gld_` prefix. Use `--expand false --compile false` to isolate
each model from upstream definitions unless the row explicitly requests expansion.

| Enabled behavior | Model | Expected evidence |
| --- | --- | --- |
| Complete-schema star expansion and redundant predicate removal | `optimizer_schema_projection` | `*` becomes the four ordered `slv_orders` outputs; `WHERE TRUE` disappears. Star expansion/qualification alone is not reported as structural optimization. |
| Constant/expression and redundant-Boolean simplification | `optimizer_constants`, `optimizer_projections` | `1 + 2` becomes `3`; `AND TRUE` disappears in the eligible projection model. `100 / 100` is not promised to fold. |
| Projection pushdown/pruning, subquery/CTE merging, dead-CTE elimination | `optimizer_projections` | Source and inspection collapse three CTEs to one SELECT; `unused_status`, the unused CTE, and wrappers disappear. |
| Source predicate pushdown | `optimizer_projections` | The outer customer filter ends up directly on `slv_orders` after wrapper merging. |
| Guarded predicate pushdown | `optimizer_predicates` | Source and inspection move the simplified outer WHERE inside the DISTINCT derived table; the DISTINCT tuple remains. |
| Bounded Boolean normalization | `optimizer_boolean_normalization` | Source and inspection change `(A AND B) OR C` to `(A OR C) AND (B OR C)`, preserving NULL logic. Expansion distance is capped at 32. |
| Guarded inner/cross join simplification | `optimizer_join_simplification` | Source and inspection attach conjunctive equalities to two inner joins; the avoidable CROSS JOIN disappears, not the three input relations. |
| Deterministic repeated-subquery factoring | `optimizer_shared_subqueries` | Source and inspection create one grouped CTE and two consumers. The consumer join and row multiplicity remain; this is not SELECT DISTINCT or a guaranteed single warehouse evaluation. |
| Wrapper/projection removal; selected-output join elimination in inspection | `optimizer_customer_profile` | Source removes `unused_first_order` and its wrapper, keeping every output and the `gld_customers` boundary. Expanded `--columns first_name` inspection can additionally prove away upstream LEFT JOIN branches. |
| Macro-aware dead projection pruning | `customer_lifetime_value`, `customer_leaderboard` | Source removes `unused_status`, `largest_order` and `returned_order_count` where unused, while preserving exact macro calls. Expanded inspection can additionally merge wrappers. |
| Pruning around ranking and DISTINCT boundaries | `customer_order_ranking`, `distinct_paying_customers` | Source removes the separate unused input status column, never the rank expression or the customer/order DISTINCT key. |
| Complementary UNION ALL scan collapse | `payment_union` | Identical scans become one scan with the original `method = 'credit_card' OR method <> 'credit_card'` filters. NULL methods still fail both comparisons, duplicates survive, and comparison coercions are retained. |
| Narrow positive EXISTS decorrelation | `high_value_customers` | A conjunctive WHERE EXISTS with one explicit equality and inner-only residual filters becomes IN over payment order IDs. Scalar AVG queries and NULL/empty behavior remain. |

Source local constant/Boolean simplification also works alongside aggregates,
windows, limits and scalar macros, without moving expressions or altering calls.
Type-changing decimal folding and overflowing integer constants are not folded.
Removing `column + 0` requires declared DuckDB INT/BIGINT input types; decimal,
computed and unknown types keep the operation. The lifetime-value demo therefore
does **not** promise removal of `p.amount + 0`: decimal addition can widen precision.
Reports explain retained arithmetic, DISTINCT tuples and movement boundaries.

Source retains conservative guards for moving expressions through aggregates,
windows, limits, set operations and outer joins. Projection deletion, filter
pushdown, join simplification and subquery factoring have separate eligibility
checks; the presence of one boundary no longer disables every independent rule.
Only a narrow positive equality-EXISTS form is decorrelated; NOT EXISTS, OR,
multiple correlation keys and correlated aggregates/limits still skip. There is
no source join elimination or assumption that an upstream stored table equals
its expanded definition. See [source optimizer safety](../../../../../docs/guides/source-optimizer-safety.md).

Inspection runs `qualify → simplify → pushdown_projections → merge_subqueries →
normalize_predicates → pushdown_safe_predicates → optimize_safe_joins →
deduplicate_subqueries → eliminate_joins → eliminate_ctes → merge_subqueries →
simplify`. Projection pushdown is disabled when a global aggregate is present;
the extra structural rules have their own guards. This is the library's explicit
rule set, **not every SQLGlot optimizer rule**. Type annotation, general expression
canonicalization, arbitrary decorrelation, and warehouse cost optimization are
not promised. Shorter SQL is not a measured speed or cost improvement.

## Inspect each focused rewrite

Compare `--optimize false` with `--optimize true` for any command below. Keep
expansion disabled first: upstream aggregation or other barriers can mask an
otherwise eligible local transformation.

```bash
extra --project-dir examples/jaffle_shop inspect gld_optimizer_schema_projection --expand false --compile false
extra --project-dir examples/jaffle_shop inspect gld_optimizer_predicates --expand false --compile false
extra --project-dir examples/jaffle_shop inspect gld_optimizer_boolean_normalization --expand false --compile false
extra --project-dir examples/jaffle_shop inspect gld_optimizer_join_simplification --expand false --compile false
extra --project-dir examples/jaffle_shop inspect gld_optimizer_shared_subqueries --expand false --compile false
extra --project-dir examples/jaffle_shop inspect gld_optimizer_customer_profile --columns first_name --expand true --compile false --optimize false
extra --project-dir examples/jaffle_shop inspect gld_optimizer_customer_profile --columns first_name --expand true --compile false --optimize true
extra --project-dir examples/jaffle_shop inspect gld_customer_lifetime_value --columns lifetime_value --expand true --compile false
extra --project-dir examples/jaffle_shop inspect gld_customer_leaderboard --columns ranked_revenue --expand true --compile false --view plan
```

With `--expand false`, `optimizer_customer_profile` stops at `gld_customers`; it
cannot prove away that model's internal joins. `--from gld_orders` is another way
to stop expanded inspection at an explicit upstream boundary. Expected boundary
messages such as `expansion disabled` and `source input` are not rewrite failures.
Never ignore a `Simplification unavailable` diagnostic when demonstrating a rule.

## Preserved boundaries and safe skips

| Model | Safety lesson |
| --- | --- |
| `gld_customer_order_ranking` | Preserve the per-customer window, amount/order-id tie-breaker, top-two filter, final ordering, and LIMIT 10. Filters must not move below the ranking boundary. |
| `gld_customer_leaderboard` | Preserve DISTINCT order rows, grouped HAVING eligibility, ranked-revenue meaning, window tie-breaker, and deterministic LIMIT 2 even when inspecting one output. |
| `gld_distinct_paying_customers` | DISTINCT applies to **customer/order pairs** before projecting customer_id. Repeated customer IDs are correct, not duplicates to remove. |
| `gld_payment_union` | Collapsing the complementary scans must preserve duplicate payments and exclude NULL methods, which match neither branch. |
| `gld_high_value_customers` | The positive WHERE membership rewrite must not multiply orders when several payments match. Scalar AVG and empty-input/NULL behavior remain intact. |
| `gld_customer_lifetime_value` | Preserve round_money Jinja and all-status payment totals for customers with orders. These are not completed-only or net recognized revenue; customers without orders are absent. |

Further guards are intentionally tested in temporary fixtures, not added as
broken dbt demo models: incomplete schemas/ambiguous bindings, duplicate outputs,
USING/NATURAL joins without complete schemas, unknown/volatile functions, dynamic
Jinja, comment loss, nonconvergence, LIMIT/OFFSET, global aggregates on empty input,
outer and OR joins, QUALIFY, DISTINCT ON, materialized/shadowed CTEs, and
order-sensitive aggregates. Seed and source YAML columns alone do not authorize
source star expansion. Incremental/history, dynamic-materialization, opaque, and
volatile upstream models remain inspection boundaries.

## Verification

The [demo regression tests](../../../../../tests/workflows/test_optimization_examples.py)
assert the actual tree changes, output names/order and exact DuckDB types
(including decimal precision/scale), source idempotence, preserved
Jinja/config, and bag-equivalent results with duplicates, NULLs, and empty inputs.
Ordered limited results are compared as sequences, not just sets. The
[inspection safety tests](../../../../../tests/workflows/test_inspection_rules.py),
[join-elimination tests](../../../../../tests/workflows/test_inspection_optimization.py),
and [source tests](../../../../../tests/sql/test_source_optimization.py) cover the
remaining guards and cross-dialect behavior.

```bash
python -m pytest tests/workflows/test_optimization_examples.py tests/workflows/test_inspection_rules.py tests/workflows/test_inspection_optimization.py tests/sql/test_source_optimization.py tests/test_documentation.py
```
