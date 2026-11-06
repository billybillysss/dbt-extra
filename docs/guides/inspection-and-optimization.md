# Inspect and optimize SQL

dbt SQL is authoritative. Neither inspection nor optimization invokes dbt,
executes arbitrary templates, accesses a warehouse, estimates cost, or guarantees speedups.

## Inspect a table or selected columns

```bash
extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue
extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --from orders
extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --view plan
extra --project-dir examples/jaffle_shop inspect customer_revenue --compile false
```

Inspection defaults to `--expand true --optimize true --compile true`. It follows statically
resolvable `ref` calls and explains the complete definition before applying the
requested projection. SQLGlot removes provably redundant joins and wrappers;
joins, filters, grouping, DISTINCT, set operations and multiplicity that affect
the selected rows remain, even when they require nonselected outputs internally.
Unsupported shapes and unknown, volatile or fallible expressions retain
boundaries without blocking unrelated safe work. See
[partial optimization](partial-optimization.md#requirements-and-boundaries) for
the evidence required for pruning, predicate movement and join changes.

Use `--optimize false` to retain the unsimplified explanation. This is more than
a list of value-lineage origins. `--from` retains selected upstream models as logical
relation inputs; other branches may still expand those shared ancestors.

Output summarizes repeated rewrite reasons by default. Add `--verbose` to see
per-rule/per-scope diagnostics and occurrence counts. This affects presentation
only: source boundaries, unresolved-relation warnings and rollback reasons remain
visible in the default output, and the SQL and safety checks are unchanged.

To copy or save SQL without CLI notices or diagnostics:

```bash
extra inspect customer_revenue --copy
extra inspect customer_revenue --output extra/sql/customer_revenue.sql
extra inspect customer_revenue --copy --output extra/sql/customer_revenue.sql
```

These options require `--view sql` and still show the explanation and warnings in
the terminal. SQL comments are preserved, but CLI logs are not copied or saved.
Relative output paths start at the dbt project root; missing directories are created.
Existing files require `--force`, and authored project inputs cannot be overwritten.
Clipboard errors leave the SQL visible (and the file saved when both options are
used). On Linux, install `wl-copy`, `xclip` or `xsel` in a desktop session; use
`--output` in headless environments.

`--compile true` resolves physical **relation names**, not arbitrary dbt Jinja or
compiled model SQL. Literal sources use their declared database/schema/identifier
(schema defaults to the source name; identifier defaults to the table name).
Source-level quoting is inherited, with table-level overrides. For example, the
Jaffle Shop customer source resolves to `main_raw.raw_customers`, not the logical
source name `jaffle_shop.customers`.

Dynamic source names and unexpanded models use resolved relation evidence from
`target/manifest.json` (or `--manifest PATH`). This preserves dbt's generated
schemas and aliases; a model's `+schema: raw` is **not** assumed to mean a physical
schema named `raw`. Manifest quoting and database qualifiers are retained. Changed
model SQL/naming configuration and conflicting literal source names are not
silently replaced by old manifest evidence. Unresolved references retain their
templates with a coverage warning. Only surviving relations are resolved after
optimization, so removed inputs do not generate resolution warnings.

Supply a current manifest for the intended target, for example from `dbt parse`.
extra does not execute profiles, environment expressions, naming macros, or dbt;
it cannot independently verify manifest target/freshness or database existence.
`--compile false` preserves `{{ source(...) }}`, `{{ ref(...) }}`, and `{{ this }}`.
The compile option is independent of expansion/optimization, also applies to
`--view plan`, and never changes authored files or the separate `optimize` command.

Inspection's `--expand true` also previews bounded static local macros, including
macros returning several columns. `--expand false` retains proven scalar calls;
unknown/multi-column output is not guessed. Literal arguments, local nested calls,
and bounded literal-list loops are supported, but dbt context, adapters, database
queries, environment access and arbitrary Jinja operations are not executed.
These previews never replace authored macro calls in source files.

Top-level literal `{% set %}`, bounded literal `{% for %}` and statically decidable
`if`/`elif`/`else` blocks use the same restricted interpreter. `ref`, `source`,
`config` and `this` remain dbt calls. Runtime-dependent blocks remain boundaries;
no values are invented for `var`, `env_var`, `run_query` or `is_incremental()`.

Unknown schemas, unsupported templates, recursive SQL, package/artifact-only
resources, and history-sensitive/incremental definitions retain explicit
boundaries with reasons. Inspection is not a claim that expanded definitions
equal the data currently stored in persisted relations. Nothing is executed.

### Simplify the logic for one selected column

Run these commands from `examples/jaffle_shop` with an installed `extra`, or
replace `extra` with `uv run extra` when using the checkout. Stop at `orders`
and keep its `ref` visible to compare the same selected output.

First, disable simplification:

```bash
extra inspect customer_revenue --columns revenue --from orders --optimize false --compile false
```

SQL output (CLI comments omitted):

```sql
SELECT
  "customer_revenue"."revenue" AS "revenue"
FROM (
  WITH order_totals AS (
    SELECT
      customer_id,
      SUM(amount) AS revenue,
      COUNT(*) AS order_count
    FROM {{ ref('orders') }}
    GROUP BY
      customer_id
  )
  SELECT
    customer_id,
    revenue + 0 AS revenue,
    order_count
  FROM order_totals
) AS "customer_revenue";
```

Then use the default simplification:

```bash
extra inspect customer_revenue --columns revenue --from orders --compile false
```

```sql
SELECT
  order_totals.revenue + 0 AS "revenue"
FROM (
  SELECT
    SUM("orders".amount) AS revenue
  FROM {{ ref('orders') }} AS "orders"
  GROUP BY
    "orders".customer_id
) AS order_totals;
```

The unused `COUNT(*) AS order_count` and `customer_id` projections are removed.
`GROUP BY customer_id` remains because it determines the rows contributing to
each revenue value. `revenue + 0` also remains: removing it requires exact type
evidence. Both commands are read-only.

### Readable aliases

Authored aliases are preserved, including short aliases such as `c` or role names
such as `buyer`. Generated aliases use logical model/source names rather than
internal analysis counters. Column-only wrappers and single-input CTEs are removed
when their removal preserves evaluation and bindings; necessary boundaries remain.

Names are generated deterministically:

1. Start with the model name or source table name; a retained selected-output
   wrapper uses the inspected model name.
2. Normalize generated names to lowercase underscore-separated words and remove
   a leading `stg_`, `brz_`, `slv_` or `gld_` layer prefix.
3. Above the 30-character target, abbreviate words left to right using a fixed
   dictionary: `customer → cust`, `customers → custs`, `transaction → txn`,
   `transactions → txns`, `revenue → rev`, `summary → sum`. Stop once it fits.
4. If still too long, retain complete leading words and append six hexadecimal
   characters derived from SHA-256 of the original name. No business roles are guessed.
5. Reserve existing identifiers, including enclosing names. On a collision, try
   the source/package context, then append `_2`, `_3`, etc. Suffixes can exceed the
   soft length target. Existing aliases and output column names are not shortened.

For example, `gld_finance_customer_lifetime_revenue_summary` becomes
`finance_cust_lifetime_rev_sum`. Expanded subqueries with long generated names
include an `Expanded from:` comment retaining the original name. Unexpanded
relations retain the full name in the relation or dbt reference itself.

## Preview authored SQL changes

```bash
extra --project-dir examples/jaffle_shop optimize --select customer_revenue --preview
```

Preview shows a diff of the actual source file and writes nothing. Applying the
command without `--preview` changes that same authored `.sql` file. Use a disposable
project copy when trying write mode on the bundled teaching inputs. Files under `target/compiled`
are not edited. `--preview` is the only no-write flag.

Literal leading `config`, static `ref` (including package/version arguments),
`source`, and supported relation-position `this` are reversibly masked, not
evaluated. Only a restricted SQLGlot rule set is used. Output names/order,
comments and SQL/Jinja round-trip checks must survive.

By default (`--expand false`), supported scalar macros are analyzed by bounded
static expansion but remain authored calls. Projection pruning accounts for
identifiers hidden in their arguments. Unsupported templates and recursive queries
retain boundaries; unknown SQL functions do not automatically skip the model.
Qualification, type and schema requirements can limit structural work while
allowing independent literal simplification or formatting.

Reports distinguish structural rewrites, qualification, formatting-only changes
and unchanged SQL. Read retained reasons and rule outcomes, not just the changed
file count. See [source optimizer safety](source-optimizer-safety.md) for enabled
rules, schema evidence, arithmetic/evaluation guards and conflict checks.

`--format pretty` puts supported leading `config()` arguments on separate lines
with indented collections; `compact` uses one line except for multiline strings.
Both preserve values, quote style, key order and supported dynamic expressions
without evaluating Jinja. Unsupported config expressions are left unchanged.

To replace macro calls in model files with expanded SQL, use:

```bash
extra --project-dir examples/jaffle_shop optimize --select macro_revenue --expand true --preview
```

Omit `--preview` to apply the expanded, optimized SQL. Expansion supports bounded
static local macros, including nested calls, multiple-column/SQL-clause output and
literal-list loops. `ref()`, `source()` and `config()` stay authored; upstream model
definitions are not inlined and macro definition files are unchanged. Unsupported
macros skip the entire model rather than writing a partial expansion. The same
binding, comment, interface and fixed-point guards apply after expansion.

Top-level static templates are preserved **byte-for-byte as a whole** by default;
the optimizer does not reconstruct or flatten their original loop/branch structure.
Explicit `--expand true` may reduce them to SQL, retaining literal dbt calls.
See [partial optimization](partial-optimization.md) for supported proofs,
diagnostic fields, recovery semantics and remaining boundaries.

## Related workflows

Use `optimize --enrich true --preview` to include missing-metadata proposals in the
same diff. See [metadata enrichment](metadata-enrichment.md) for the YAML example
and inference limits, and the [optimizer walkthrough](../../examples/jaffle_shop/models/gld/optimization/README.md)
for focused rewrite examples. Run dbt parsing, tests and builds independently
after reviewing any source changes.
