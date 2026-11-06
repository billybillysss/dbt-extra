# Native Jaffle Shop

This dbt project is the dbt-extra example. SQL and dbt properties are authoritative; the
optional `extra_project.yaml` contains tool settings only. No compilation or
warehouse connection is required for dbt-extra.

This single project combines the small revenue walkthrough with the classic
Jaffle Shop models, metadata, tests, macros, and customer-history snapshot:

- `demo_raw_orders` → `orders` → `customer_revenue` → `macro_revenue` is the
  four-row walkthrough. Revenue includes completed orders only.
- `stg_customers` → `customer_details` → `customer_profile` traces a name through
  three models. Selected-column inspection removes its redundant CTE and wrappers.
- `raw_customers`, `raw_orders`, and `raw_payments` feed the `brz_*`, `slv_*`,
  and `gld_*` models. Their lifetime-value totals include payments across all
  order statuses, not net recognized revenue. See [seed provenance](seeds/README.md).
- `models/gld/capabilities` and `models/gld/optimization` retain the larger SQL
  demonstrations. The configured finance export view selects the gold models.

From the repository root, using an installed `extra` (or `uv run extra` in a
source checkout):

```bash
extra --project-dir examples/jaffle_shop validate
extra --project-dir examples/jaffle_shop inspect customer_profile --columns customer_name
extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue
extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --from orders
extra --project-dir examples/jaffle_shop export --format xlsx
extra --project-dir examples/jaffle_shop import examples/jaffle_shop/extra/review/review.xlsx --preview
extra --project-dir examples/jaffle_shop optimize --select customer_revenue --preview
extra --project-dir examples/jaffle_shop enrich --select customer_revenue --preview
```

## Trace a customer name

From this directory in the source checkout:

```bash
uv run extra inspect customer_profile --columns customer_name
```

The selected name simplifies to its source expression (CLI comments omitted;
without optional dbt artifacts):

```sql
SELECT
  TRIM("customers".first_name) AS "customer_name"
FROM main_raw.raw_customers AS "customers";
```

<details>
<summary>What is removed, and what stays?</summary>

The original models retain their unused customer attributes and `customer_input`
CTE as teaching inputs. Inspection follows `first_name` through the rename,
removes the redundant CTE and column-only wrappers, and preserves `TRIM`.
Authored files are unchanged. Generated aliases identify inputs rather than
internal counters. A manifest can add database qualifiers and quoting.

The revenue example retains the completed-order filter, decimal cast, customer
grouping and necessary evaluation boundaries. Simplification does not promise
to remove every CTE or subquery from every model.

</details>

## More examples

`macro_revenue` demonstrates a local scalar macro: reviews show the original call
as `macro.round_money(...)`; `extra export --expand` previews its generated SQL.
Runtime-dependent macros remain opaque. Optimization preserves calls by default;
`optimize --expand true --preview` proposes replacing supported static calls with
SQL. Named macro
blocks remain editable alongside their YAML documentation in the same review row.
`round_money(expression, decimal_places=2)` supports both walkthroughs.

Keep `models/gld/optimization` in its pre-optimization teaching form, including
redundant CTEs, unused columns, and constant expressions. Preview changes with
`extra --project-dir examples/jaffle_shop optimize --select 'path:models/gld/optimization/**' --preview`;
apply rewrites only to a temporary copy of the project.
The [optimizer walkthrough](models/gld/optimization/README.md) maps every enabled
rule to a focused demo and distinguishes source edits, read-only inspection,
macro-aware pruning, preserved boundaries, and safe skips. Stable before-inputs in
`tests/fixtures/optimization` let regression tests verify source rewrites
even after a local example has been optimized.

`rounded_total` uses Jinja filters/dictionary options, while
`hash_relation_attributes` introspects the adapter at dbt runtime; these stay opaque
to offline SQL analysis. They are still included in reviews and run normally in dbt.

For workbook grouping, editable fields, reversible macro shorthand and baseline
rules, see the [review contract](../../docs/reference/catalogs.md). For the
four-property YAML proposal, see [metadata enrichment](../../docs/guides/metadata-enrichment.md).

Execute dbt independently, if desired:

```bash
dbt build --project-dir examples/jaffle_shop --profiles-dir examples/jaffle_shop
dbt docs generate --project-dir examples/jaffle_shop --profiles-dir examples/jaffle_shop
```

The in-memory DuckDB target requires one `dbt build` invocation so seeds and models
share its connection lifecycle. dbt-extra never runs that command for you.
Both datasets have reconciliation tests in `tests/`; the classic seeds load into
`main_raw`, matching the `jaffle_shop` source definitions. The later docs command
starts a fresh in-memory connection, so it does not retain warehouse catalog data.
