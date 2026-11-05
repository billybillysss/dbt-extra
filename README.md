<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/dbt-extra-mark-dark.svg">
    <img src="docs/assets/dbt-extra-mark.svg" alt="dbt-extra — Modular joint icon" width="128" height="128">
  </picture>
</p>

<h1 align="center">dbt-extra — dbt transformation review and inspection</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-0D9488" alt="License: MIT"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/billybillysss/dbt-extra/actions/workflows/ci.yml"><img src="https://github.com/billybillysss/dbt-extra/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="docs/index.md"><img src="https://img.shields.io/badge/docs-read-0D9488" alt="Documentation"></a>
</p>

<p align="center">
  <a href="docs/getting-started.md">Get started</a> · <a href="docs/index.md">Documentation</a> · <a href="docs/guides/ai-assisted-workflow.md">AI-assisted workflow</a> · <a href="examples/jaffle_shop/README.md">Native dbt demo</a> · <a href="CONTRIBUTING.md">Contributing</a>
</p>

**Trace a dbt column back to its SQL. Review transformations in Excel.
Preview edits to the original files—all offline.**

Where does `revenue` come from? Which filters change it? Can a reviewer update
its description without hunting through YAML? dbt-extra helps answer those questions
using the dbt project you already have. No warehouse credentials, dbt compilation,
or second model language required.

## See where a column comes from

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). From a terminal:

```bash
git clone https://github.com/billybillysss/dbt-extra.git
cd dbt-extra
uv sync --locked
cd examples/jaffle_shop
uv run extra inspect customer_revenue --columns revenue --compile false
```

The bundled example follows `customer_revenue → orders → demo_raw_orders`.
The explanation retains the **completed-order filter**, **decimal cast** and
**per-customer grouping**, even though you selected only `revenue`.

<details>
<summary>See the SQL output (CLI comments omitted)</summary>

```sql
SELECT
  "extra_selected_output"."revenue" AS "revenue"
FROM (
  WITH order_totals AS (
    SELECT
      SUM(CAST("extra_input_2".amount AS DECIMAL(12, 2))) AS revenue
    FROM {{ ref('demo_raw_orders') }} AS "extra_input_2"
    WHERE
      "extra_input_2".status = 'completed'
    GROUP BY
      "extra_input_2".customer_id
  )
  SELECT
    order_totals.revenue + 0 AS revenue
  FROM order_totals AS order_totals
) AS "extra_selected_output";
```

This is a definition explanation, not executed SQL or proof about stored data.
The seed remains an explicit boundary. Authored files are unchanged.

</details>

Stop at an upstream model with `--from orders`, or use `--view plan` for a logical
tree. [Try the walkthrough →](docs/getting-started.md)

> **Private preview · 0.2.0:** install from this checkout with repository access.
> The executable is `extra`; Python imports use `dbt_extra`.

## Pick your workflow

| Feature | What it does | Writes by default |
| --- | --- | --- |
| [`init`](#use-your-existing-dbt-project) | Add optional tool settings to an existing dbt project; refuse overwrite. | New `extra_project.yaml` only |
| [`validate`](#validate-offline) | Check local resources, Jinja structure, supported static SQL and reference cycles. | Nothing |
| [`inspect`](#inspect-sql-columns-and-logical-plans) | Explain full models or selected columns, keeping filters, joins, grouping and row multiplicity. | Nothing |
| [`export`](#review-in-excel-or-csv-apply-through-a-diff) | Export folder-grouped XLSX, flat CSV, or read-only JSON analysis. | Review outputs only |
| [`import`](#review-in-excel-or-csv-apply-through-a-diff) | Patch supported review edits back to their original dbt files, with baseline checks. | Original SQL/YAML |
| [`optimize`](#preview-authored-sql-cleanup) | Conservatively rewrite authored SQL; optionally expand local macros. | Selected model SQL |
| [`enrich`](#fill-missing-metadata-with-real-yaml) | Fill missing inferred types and safe passthrough descriptions. | Existing dbt property YAML |

**Every writing command supports `--preview`, which writes
nothing—not even output directories or temporary files.** Without it, the writes
listed above apply. The examples below run from `examples/jaffle_shop` after the
setup above. They use `extra`; with this checkout, use `uv run extra` instead
(uv finds the repository environment from subdirectories). `--locked` is only
needed on the installation command shown above.

Jump to [project settings](#use-your-existing-dbt-project) ·
[inspection](#inspect-sql-columns-and-logical-plans) ·
[Excel/CSV](#review-in-excel-or-csv-apply-through-a-diff) ·
[JSON/AI](#export-read-only-analysis-for-an-ai-assistant) ·
[optimization](#preview-authored-sql-cleanup) ·
[YAML enrichment](#fill-missing-metadata-with-real-yaml) ·
[selectors](#select-models-folders-and-tags) · [Python](#python-api).

## Use your existing dbt project

There is one project root: the directory containing `dbt_project.yml`. Run inside
that project (or a subdirectory), and supply its actual SQL dialect:

```bash
cd path/to/your/dbt_project
extra --dialect snowflake inspect your_model --columns your_column
```

When running outside the project, choose it once with the environment variable:

```bash
export EXTRA_PROJECT_DIR=/path/to/your/dbt_project
extra --dialect snowflake inspect your_model --columns your_column
```

In PowerShell, use `$env:EXTRA_PROJECT_DIR = 'C:\path\to\your\dbt_project'`.
For a one-off override, put `--project-dir PATH` **before** the command:
`extra --project-dir /path/to/your/dbt_project --dialect snowflake validate`.
Use an installed `extra` outside this checkout, or invoke its environment explicitly.

dbt SQL and property YAML remain the source of truth. No initialization is
required. Optional `extra_project.yaml` sits beside `dbt_project.yml` and stores
tool settings only. This example
uses Jaffle Shop's DuckDB dialect and gold-model finance view, with explicit
settings for each workflow:

```yaml
version: 2
analysis:
  dialect: duckdb
inspection:
  expand: true
  optimize: true
  compile: true
  boundaries: []
export:
  format: xlsx
  output_dir: extra/review
  expand: false
  select:
    - 'path:models/gld/**'
  views:
    finance:
      select:
        - 'path:models/gld/**'
optimization:
  format: pretty
  expand: false
  enrich: false
metadata:
  select:
    - customer_revenue
```

To preview a starter settings file in **your own project without one**:

```bash
extra --dialect snowflake init --preview
```

Remove `--preview` to create it. `init` requires an existing `dbt_project.yml` and
refuses to overwrite settings; Jaffle Shop already has
[`extra_project.yaml`](examples/jaffle_shop/extra_project.yaml).

**Project selection:** `--project-dir` > `EXTRA_PROJECT_DIR` > nearest
`dbt_project.yml` upward from the current directory. Explicit directories must
contain that file; only automatic discovery searches parents. Settings never
redirect discovery; legacy `dbt.project_dir` is rejected with migration guidance.
`init` uses this same root and takes no directory argument.

**Option precedence:** explicit CLI values > settings > discoverable dbt evidence
> defaults. Explicit selection lists replace configured lists rather than append.
CLI input paths (`import PATH`, `--manifest PATH`, and project directories) are
relative to the **current directory**; configured paths and export destinations
are relative to the **project root**. Absolute paths stay absolute.

No manifest, catalog or warehouse connection is required for the native demo.
For an existing project, optional `dbt.artifacts.manifest` and
`dbt.artifacts.catalog` settings add evidence; explicitly configured paths must
exist. `--manifest PATH` supplies manifest evidence on the CLI. A discovered
`target/manifest.json` is used when present. Use artifacts for the intended target:
they do not verify current warehouse state. `analysis.dialect: auto` uses the
manifest adapter; without a resolved dialect, SQL operations require an explicit
choice rather than guessing.

See [configuration](docs/reference/configuration.md) and the
[existing-project guide](docs/guides/existing-dbt-project.md).

## Validate offline

```bash
extra validate
```

Validation checks local structure, supported static SQL and dependency cycles.
Unavailable SQL analysis is reported with a reason; it is not silently counted
as executed validation. This does **not** run `dbt parse`, `dbt compile`,
`dbt build`, data tests, warehouse SQL validation, or enforced-contract checks.

## Inspect SQL, columns and logical plans

```bash
# Full model definition.
extra inspect customer_revenue
# Follow two outputs, but stop at the upstream orders model.
extra inspect customer_revenue --columns customer_id revenue --from orders --compile false
# Show a logical tree instead of SQL.
extra inspect customer_revenue --columns revenue --view plan --compile false
# Keep local relation boundaries and turn logical optimization off.
extra inspect customer_revenue --expand false --optimize false --compile false
```

- `--columns` and `--from` accept multiple or repeated values. `--from` boundaries
  must be upstream models, not arbitrary unrelated resources.
- Defaults are `--expand true --optimize true --compile true --view sql`.
  Expansion follows supported upstream model definitions and bounded static local
  macros. Incremental/history and opaque runtime-dependent logic remain boundaries.
- `--compile true` resolves physical relation names **offline**, using available
  source/manifest evidence. It never runs `dbt compile`, reads execution profiles,
  or verifies that a relation exists. `--compile false` keeps `ref`/`source` calls.
- A selected output still retains logic affecting its rows and values: joins,
  predicates, DISTINCT tuples, aggregation, windows and limits. Unknown coverage
  remains explicit; an unavailable simplification is not a successful rewrite.

All inspection is read-only. The result explains a definition, not stored-table
equivalence or a warehouse execution plan. See
[inspection and optimization](docs/guides/inspection-and-optimization.md).

### Simplify the logic for one selected column

`customer_revenue` defines `customer_id`, `revenue` and `order_count`. To focus on
`revenue`, compare the selected-column explanation before and after simplification.
Stop at `orders` to keep the comparison short; `--compile false` keeps its `ref`.

**Before: select `revenue`, but leave the explanation unsimplified.**

```bash
extra inspect customer_revenue --columns revenue --from orders --optimize false --compile false
```

SQL output (CLI comments omitted):

```sql
SELECT
  "extra_selected_output"."revenue" AS "revenue"
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
) AS "extra_selected_output";
```

**After: simplify the selected-column explanation (the default).**

```bash
extra inspect customer_revenue --columns revenue --from orders --compile false
```

SQL output (CLI comments omitted):

```sql
SELECT
  "extra_selected_output"."revenue" AS "revenue"
FROM (
  WITH order_totals AS (
    SELECT
      SUM("extra_input_1".amount) AS revenue
    FROM {{ ref('orders') }} AS "extra_input_1"
    GROUP BY
      "extra_input_1".customer_id
  )
  SELECT
    order_totals.revenue + 0 AS revenue
  FROM order_totals AS order_totals
) AS "extra_selected_output";
```

- **Removed:** the unused `COUNT(*) AS order_count` and unneeded `customer_id`
  projections.
- **Preserved:** `SUM(amount)` and `GROUP BY customer_id`, because grouping still
  determines revenue even when the grouping column is not selected.
- **Not assumed redundant:** `revenue + 0` remains because removing it requires
  suitable exact type evidence.

This simplifies the explanation only. `inspect` never edits model files; the
separate `optimize` command previews or applies authored SQL changes.

## Review in Excel or CSV, apply through a diff

```bash
extra export --format xlsx --select customer_revenue
# Edit supported cells in extra/review/review.xlsx, then close Excel.
extra import extra/review/review.xlsx --preview
# After reviewing the diff, apply those same edits.
extra import extra/review/review.xlsx
```

XLSX is the default. The workbook groups native folders into sheets and collapsible
`TABLE → STEP / OUTPUT → COLUMN` rows. Sources use `SOURCE → TABLE → COLUMN`;
macros, seeds and snapshots have their own groups. Frozen identity columns,
filters, a README legend and unlocked cells make supported edits visible.

| Review area | Supported edits |
| --- | --- |
| Model and final-output metadata | Descriptions, types, tests, constraints, config, meta and arbitrary authored properties. |
| STEP / OUTPUT SQL | Supported SELECT clauses, DISTINCT controls and explicit projection expressions at their original scope. |
| Hidden `Authored SQL` | Full local model SQL/Jinja; use full SQL **or** structured edits for a model, not both. |
| Macros | Named macro-block SQL plus existing YAML documentation and arguments. |
| Sources, seeds and snapshots | Supported authored metadata; local SQL snapshots also expose authored SQL. |
| `Configuration` sheet | Nonempty authored model/seed/snapshot scopes in `dbt_project.yml`, preserving child scopes. |

Identity/location columns, CTE column metadata, package/artifact-only resources and
generated SQL are read-only. Config/Meta/Properties cells use JSON objects;
Tests/Constraints use JSON arrays. Imports preserve existing `tests` versus
`data_tests` spelling. No row additions/deletions, renames or path moves are supported.

### CSV and isolated output directories

```bash
extra export --format csv --select customer_revenue --output-dir extra/review-csv
extra import extra/review-csv --preview
```

CSV exports `resources.csv`, `columns.csv` and `_baseline.json`. Import the
**whole directory**, not a single CSV. `--output-dir` (alias `--path`) is relative
to the dbt project unless absolute; separate directories keep reviews isolated.
Use a spreadsheet's text-import mode for untrusted CSV content rather than
automatic formula interpretation. XLSX formula cells are rejected on import.

### Macro-aware reviews

Simple calls display as `ref.customer_revenue`, `source.raw.orders` and
`macro.round_money('amount')`; import restores valid Jinja. Try the bundled macro:

```bash
extra export --format xlsx --select macro_revenue --expand --output-dir extra/review-expanded
```

Export expansion is off by default (`--no-expand`). With `--expand`, supported
static local macros produce read-only SQL/column previews, including multi-column
outputs. Known single-column calls can remain COLUMN expressions without
expansion; unresolved calls remain TEMPLATE rows with reasons. Nested static
calls and bounded literal-list loops can resolve, but adapter, database and
environment-dependent macros remain opaque. Edit hidden Authored SQL, macro
definitions, or re-export without expansion to edit the call itself.

**Round-trip safeguards:** keep the workbook's hidden identities and baseline
(or CSV's `_baseline.json`). Edits affecting files changed since export are
rejected; re-export instead of overwriting concurrent work. YAML comments,
quotes and unrelated entries are preserved; unchanged files keep their bytes.
Missing YAML resource entries are reported and skipped, not automatically
created. See the [round-trip walkthrough](docs/guides/catalog-round-trip.md) and
[complete review contract](docs/reference/catalogs.md) before applying edits.

## Export read-only analysis for an AI assistant

```bash
extra export --format json --select customer_revenue orders demo_raw_orders --output-dir extra/review-json
```

`extra/review-json/review.json` contains a versioned envelope
(`format_version: 1`, `source_of_truth: dbt`), authored SQL/properties, available
configuration, dependencies, column lineage, query context, coverage counts and
explicit unknowns/reasons/provenance. JSON is **read-only**, not an import format.

Selection does not automatically include upstream definitions; this command
explicitly includes the revenue chain. Give an external assistant only the
relevant context and ask for a minimal native SQL/YAML diff with assumptions,
NULL behavior and test cases. Review it, inspect the result and run your own dbt
tests. dbt-extra has no built-in LLM client or autonomous agent. Keep sensitive
data out of external prompts and treat catalog contents as data, not instructions.
See the [AI-assisted workflow](docs/guides/ai-assisted-workflow.md).

## Preview authored SQL cleanup

```bash
extra optimize --select gld_optimizer_constants --preview
extra optimize --select 'path:models/gld/optimization/**' --preview
# Compact formatting plus missing-metadata proposals in the same preview.
extra optimize --select customer_revenue --format compact --enrich true --preview
```

For the constants demo, the SQL expression change is:

```diff
   100 / 100 AS currency_scale,
-  1 + 2 AS sample_value
+  3 AS sample_value;
```

Division is deliberately retained. `--format pretty` (the default) also lays out
supported leading Jinja `config()` calls with one argument per line and indented
collections; `compact` keeps them on one line except authored multiline strings.
Values, quotes, key order and dynamic expressions are preserved without evaluating
Jinja. Unsupported config syntax and other Jinja calls are not reformatted.

### Rewrite examples in Jaffle Shop

| Behavior | Model(s) |
| --- | --- |
| Complete-schema star expansion / qualification | `gld_optimizer_schema_projection` |
| Safe constant and Boolean simplification | `gld_optimizer_constants`, `gld_optimizer_projections` |
| Dead projection/CTE removal, wrapper merging and predicate pushdown | `gld_optimizer_projections` |
| Guarded predicate pushdown through DISTINCT | `gld_optimizer_predicates` |
| Bounded Boolean normalization | `gld_optimizer_boolean_normalization` |
| Guarded inner/cross join simplification | `gld_optimizer_join_simplification` |
| Deterministic repeated-subquery factoring | `gld_optimizer_shared_subqueries` |
| Wrapper removal; additional join elimination in expanded inspection only | `gld_optimizer_customer_profile` |
| Macro-aware pruning of unused columns/aggregates | `gld_customer_lifetime_value`, `gld_customer_leaderboard` |
| Pruning without changing ranking or DISTINCT keys | `gld_customer_order_ranking`, `gld_distinct_paying_customers` |
| Complementary UNION ALL scan collapse, preserving duplicates and NULL filtering | `gld_payment_union` |
| Narrow positive equality-EXISTS to membership rewrite | `gld_high_value_customers` |

These are **14 focused models**, not every possible SQLGlot optimization. The
[optimizer walkthrough](examples/jaffle_shop/models/gld/optimization/README.md)
maps the precise rules, evidence and safety boundaries. Keep these teaching inputs
unchanged: preview here and apply rewrites only on a disposable project copy.

Source optimization preserves output names/order, comments and authored dbt calls
by default (`--expand false`). Use `extra optimize --select macro_revenue --expand true --preview`
to review replacing supported static local macros with SQL; omit `--preview` to
write the expanded, optimized SQL. `ref()`, `source()` and `config()` calls remain
authored. Unsupported macros skip the model unchanged. Optimization does not eliminate joins.
Ambiguous schemas, unsafe/opaque expressions and nonconvergent rewrites skip with
reasons. Reports distinguish structural rewrites, qualification, formatting-only
changes and unchanged models, and explain retained arithmetic or row boundaries.
A formatting diff is **not** a structural rewrite; shorter SQL is **not** a measured
warehouse speedup. See [source optimizer safety](docs/guides/source-optimizer-safety.md).

## Fill missing metadata with real YAML

```bash
extra enrich --select customer_revenue --preview
```

The following excerpts come directly from
[`models/schema.yml`](examples/jaffle_shop/models/schema.yml) and the enrichment
proposal for the bundled project. Other models, seeds and unrelated metadata are
omitted here; this is dbt property YAML, **not** `extra_project.yaml` settings.

**Before:**

```yaml
version: 2
models:
  - name: customer_revenue
    description: Completed-order revenue per customer, not a governed metric definition.
    config:
      meta:
        owner: finance
    columns:
      - name: customer_id
      - name: revenue
      - name: order_count
```

**After accepting the proposal:**

```yaml
version: 2
models:
  - name: customer_revenue
    description: Completed-order revenue per customer, not a governed metric definition.
    config:
      meta:
        owner: finance
    columns:
      - name: customer_id
        data_type: BIGINT
        description: Customer identifier.
      - name: revenue
        data_type: DECIMAL(12, 2)
      - name: order_count
        data_type: BIGINT
```

The preview reports **4 missing properties inferred; 2 unresolved**: three types
plus the unambiguous passthrough description of `customer_id`. It does not invent
descriptions for transformed `revenue` or `order_count`. Existing authored values
are never overwritten. Apply on your review branch by removing `--preview`.

Enrichment can add inferred columns inside an **existing writable model entry**,
but it does not generate new properties files or missing model entries. Add those
entries in dbt first and retry; read-only/versioned metadata is skipped with a
reason. `optimize --enrich true` combines SQL and metadata proposals.

## SQL dialect and function coverage

dbt-extra uses SQLGlot for SQL parsing and function support, with additional
implementations for functions SQLGlot does not recognize.

| dbt adapter | SQL dialect | Additional function support |
| --- | --- | --- |
| DuckDB | `duckdb` | SQLGlot only |
| PostgreSQL | `postgres` | SQLGlot only |
| Snowflake | `snowflake` | SQLGlot only |
| BigQuery | `bigquery` | SQLGlot only |
| Spark / Fabric Spark (`fabricspark`) | `spark` | [86 function gaps implemented](docs/reference/sql-functions/spark.md) |
| SQL Server (`sqlserver`) | `tsql` | [76 function gaps implemented](docs/reference/sql-functions/tsql.md) |
| Fabric Warehouse | `fabric` | SQLGlot only |
| Databricks | `databricks` | SQLGlot only |
| Redshift | `redshift` | SQLGlot only |
| Trino | `trino` | SQLGlot only |
| Athena | `athena` | SQLGlot only |

These dialects have shared SQL regression coverage; warehouse execution checks
currently cover DuckDB only. Other SQLGlot dialects can be selected explicitly.

Additional function support fills recognition and analysis gaps in SQLGlot
30.29.0—not missing warehouse functionality. Some return types remain unresolved.
See the [function reference](docs/reference/sql-functions/README.md) for details.

## Select models, folders and tags

`export`, `optimize` and `enrich` accept repeatable `--select` (`-s`) and
`--exclude`, each with multiple values:

```bash
extra export --select orders customer_revenue --preview
extra export --select 'path:models/gld/**' --exclude macro_revenue --preview
extra export --select 'tag:finance' --preview
extra optimize --select model.jaffle_shop.customer_revenue --preview
# Use the bundled named view: all gold models, without writing a workbook.
extra export --view finance --preview
```

Supported forms are names/globs, exact resource IDs, `name:`, `id:`, `path:`,
`tag:`, `package:` and `resource_type:`. Quote globs so the shell does not expand
them. This is a subset of dbt selection: graph operators and intersections are
not supported. Optimization and enrichment act on SQL models, not source/group
metadata. A named export view overrides base format/select/exclude/expand
settings; explicit flags override the view. See the [CLI reference](docs/reference/cli.md).

## Python API

```python
from dbt_extra import Project
from dbt_extra.analysis import catalog
from dbt_extra.optimization import optimize

project = Project()  # Same root discovery as the CLI; or Project("/path/to/project").
document = catalog(project, project.select(["customer_revenue"]))
changes, skipped = optimize(project, select=["customer_revenue"])
print(changes.diffs())
# changes.apply()  # Explicitly accept the proposed source edits.
```

The CLI is the preferred entry point; Python integrations should pin and test
versions. See [architecture](docs/development/architecture.md) for module boundaries.

## Safety and maturity

extra is pre-1.0 and conservative by design:

- **Unknowns stay explicit.** Coverage depends on dialect, schemas and Jinja.
  Bounded static local macros can be previewed; runtime/adapter-dependent macros
  remain opaque. Only explicit `optimize --expand true` (or `optimization.expand: true`)
  replaces supported authored macro calls with generated SQL.
- **dbt still owns execution.** dbt-extra is not a dbt engine, metrics service or
  warehouse optimizer. Inspection explains definitions, not equivalence to
  persisted or incremental relations. Run your own dbt parsing, tests and builds.
- **Writes still need review.** Package/artifact-only resources and inherited
  version properties are read-only. Full opaque-template edits are structure-checked,
  not dbt-compiled. Baseline checks and rollback attempts are not crash-safe
  multi-file transactions or file locks.

See [compatibility](docs/compatibility.md) and the
[production adoption checklist](docs/guides/production-workflow.md).

## Help shape dbt-extra

Try one model from your own project. If analysis stops, share a **minimal redacted
reproduction** and the coverage reason in an
[issue](https://github.com/billybillysss/dbt-extra/issues). Dialect edge cases,
documentation improvements and regression tests are especially useful.
Read [Contributing](CONTRIBUTING.md) to get started; report vulnerabilities through
the [security policy](SECURITY.md), not a public bug report.

[Get started](docs/getting-started.md) · [CLI](docs/reference/cli.md) ·
[Configuration](docs/reference/configuration.md) · [Review contract](docs/reference/catalogs.md) ·
[Inspection and optimization](docs/guides/inspection-and-optimization.md) ·
[Native example](examples/jaffle_shop/README.md) · [Contributing](CONTRIBUTING.md)
