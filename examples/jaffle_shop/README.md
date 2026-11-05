# Native Jaffle Shop

This is the current dbt-extra example. SQL and dbt properties are authoritative; the
optional `extra_project.yaml` contains tool settings only. No compilation or
warehouse connection is required for dbt-extra.

This single project combines the small revenue walkthrough with the classic
Jaffle Shop models, metadata, tests, macros, and customer-history snapshot:

- `demo_raw_orders` → `orders` → `customer_revenue` → `macro_revenue` is the
  four-row walkthrough. Revenue includes completed orders only.
- `raw_customers`, `raw_orders`, and `raw_payments` feed the `brz_*`, `slv_*`,
  and `gld_*` models. Their lifetime-value totals include payments across all
  order statuses, not net recognized revenue. See [seed provenance](seeds/README.md).
- `models/gld/capabilities` and `models/gld/optimization` retain the larger SQL
  demonstrations. The configured finance export view includes all 24 gold models.

All 31 models are authored native dbt SQL. There is no nested generated dbt
project or legacy model-definition/catalog workflow.

From the repository root:

```bash
extra --project-dir examples/jaffle_shop validate
extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue
extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --from orders
extra --project-dir examples/jaffle_shop export --format xlsx
extra --project-dir examples/jaffle_shop import examples/jaffle_shop/extra/review/review.xlsx --preview
extra --project-dir examples/jaffle_shop optimize --select customer_revenue --preview
extra --project-dir examples/jaffle_shop enrich --select customer_revenue --preview
```

`macro_revenue` demonstrates a local scalar macro: reviews show the original call
as `macro.round_money(...)`; `extra export --expand` previews its generated SQL.
Runtime-dependent macros remain opaque, and optimization does not expand calls. Named macro
blocks remain editable alongside their YAML documentation in the same review row.
`round_money(expression, decimal_places=2)` supports both walkthroughs.

Keep `models/gld/optimization` in its pre-optimization teaching form, including
redundant CTEs, unused columns, and constant expressions. Preview changes with
`extra --project-dir examples/jaffle_shop optimize --select 'path:models/gld/optimization/**' --preview`;
apply rewrites only to a temporary copy of the project.
The [optimizer walkthrough](models/gld/optimization/README.md) maps every enabled
rule to a focused demo and distinguishes source edits, read-only inspection,
macro-aware pruning, preserved boundaries, and safe skips. Stable before-inputs in
`tests/fixtures/optimization` let regression tests verify all 14 source rewrites
even after a local example has been optimized.

`rounded_total` uses Jinja filters/dictionary options, while
`hash_relation_attributes` introspects the adapter at dbt runtime; these stay opaque
to offline SQL analysis. They are still included in reviews and run normally in dbt.

The same shorthand works inside column expressions, for example
`CASE WHEN revenue > 0 THEN macro.round_money('revenue') ELSE 0 END`.
Imports restore the Jinja call. Known single-column calls (including aggregate and
window expressions) stay COLUMN expressions even alongside unresolved macros.
Expansion derives column mappings from generated SQL without extra TEMPLATE rows;
only unresolved calls remain TEMPLATE rows with reasons. Generated SQL is read-only:
edit hidden Authored SQL or the macro definition, or re-export without expansion.

The XLSX groups native model paths into sheets with collapsible
`TABLE → STEP / OUTPUT → COLUMN` rows. `Configuration` edits nonempty authored dbt project scopes,
not dbt-extra defaults. Full model SQL is in the hidden `Authored SQL` column.
Identity columns start with `Type`, `Path`, `Name`, using folders like `models/slv`.
`Package` identifies the owning dbt project/package. Snapshot table summaries have
a distinct fill, following configured snapshot roots. Effective Config, Snapshot,
and custom References columns are omitted; official relationships remain in Tests
and Constraints, and arbitrary metadata is preserved.

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
