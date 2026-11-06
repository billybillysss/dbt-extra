<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/dbt-extra-mark-dark.svg">
    <img src="docs/assets/dbt-extra-mark.svg" alt="dbt-extra — Modular joint icon" width="128" height="128">
  </picture>
</p>

<h1 align="center">dbt-extra</h1>

<p align="center">
  <a href="https://pypi.org/project/dbt-extra/"><img src="https://img.shields.io/pypi/v/dbt-extra?color=0D9488" alt="PyPI version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-0D9488" alt="License: MIT"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/billybillysss/dbt-extra/actions/workflows/ci.yml"><img src="https://github.com/billybillysss/dbt-extra/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="docs/index.md"><img src="https://img.shields.io/badge/docs-read-0D9488" alt="Documentation"></a>
</p>

**Understand, optimize, and review dbt SQL—without running dbt.**

dbt-extra is a Python library and CLI for working with existing dbt projects locally.
Trace column logic through upstream models, simplify and optimize supported SQL,
and review or edit SQL and metadata in Excel or CSV.

Preview proposed changes before applying them to your original SQL and YAML files.
Your dbt project remains the source of truth.

No initialization or warehouse connection is required. dbt-extra reads authored
dbt files and optional artifacts without running dbt or executing arbitrary Jinja.

| Understand | Optimize | Review together |
| --- | --- | --- |
| Follow a column across models and see simplified SQL | Preview guarded rewrites to authored model files | Edit supported Excel/CSV fields, then review the SQL/YAML diff |

## Install and try it

Requires Python 3.11+. Install the standalone CLI with
[uv](https://docs.astral.sh/uv/):

```bash
uv tool install dbt-extra
extra --version
```

Already have a dbt project? Run inside it, replacing the dialect, model and column
with your own:

```bash
extra --dialect snowflake inspect your_model --columns your_column
extra --dialect snowflake optimize --select your_model --preview
extra --dialect snowflake export --format xlsx --select your_model
```

Install from [PyPI](https://pypi.org/project/dbt-extra/) in an existing uv-managed
Python project:

```bash
uv add dbt-extra
uv run extra --version
```

The executable is `extra`; Python imports use `dbt_extra`.

### Try the bundled demo

From a source checkout (repository access is required while the repository is
private):

```bash
git clone https://github.com/billybillysss/dbt-extra.git
cd dbt-extra
uv sync --locked
cd examples/jaffle_shop
uv run extra inspect customer_profile --columns customer_name
uv run extra optimize --select gld_optimizer_projections --preview
uv run extra export --format xlsx --select customer_revenue
```

The first command follows a column through three models to its cleaning expression:

```sql
SELECT
  TRIM("customers".first_name) AS "customer_name"
FROM main_raw.raw_customers AS "customers";
```

The second previews unused-column and CTE removal in an authored model; the third
creates an editable review workbook. Inspection and optimization previews change
no files and execute no SQL.

For the complete **three models → readable SQL → optimizer diff → Excel edit →
YAML diff** demonstration, see the [five-step demo](docs/guides/five-step-demo.md).
Its runnable script uses a temporary project copy and needs neither Excel nor dbt
installed.

The examples below run from `examples/jaffle_shop` unless noted. Inspection and
previews are read-only; export creates review files. Use a disposable project copy
or review branch before applying source changes.

## Features

| Command | Purpose | Writes without `--preview` |
| --- | --- | --- |
| [`inspect MODEL`](#inspect-model-and-column-logic) | Explain model or selected-column SQL; show a logical plan | Nothing |
| [`optimize`](#optimize-authored-sql) | Rewrite authored SQL; optionally expand static local macros | Selected model SQL |
| [`export`](#review-and-edit-in-excel) | Export folder-grouped XLSX, flat CSV or read-only JSON | Review files |
| [`import PATH`](#review-and-edit-in-excel) | Apply supported review edits with baseline checks | Original SQL/YAML |
| [`enrich`](#fill-missing-column-metadata) | Fill missing inferred types and passthrough descriptions | Existing dbt property YAML |
| [`validate`](#validate-a-project) | Check local structure, supported static SQL and reference cycles | Nothing |
| [`init`](#configure-an-existing-project) | Create optional tool settings in an existing dbt project | New `extra_project.yaml`; refuses overwrite |

Every writing command supports `--preview`, which writes nothing, including
directories and temporary files. Review source diffs before applying them.

The [Python API](#use-the-python-api) also supports project analysis, column
lineage, review workflows, explicit change proposals and standalone SQL optimization.

## Inspect model and column logic

### Trace a column through multiple dbt layers

Trace `customer_profile.customer_name` through three models in the bundled
[Jaffle Shop project](examples/jaffle_shop/README.md):

```bash
uv run extra inspect customer_profile --columns customer_name
```

Inspection follows the rename back to the original name-cleaning expression,
removing redundant CTEs, subqueries and unused outputs. SQL output (CLI comments
omitted; without optional dbt artifacts):

```sql
SELECT
  TRIM("customers".first_name) AS "customer_name"
FROM main_raw.raw_customers AS "customers";
```

<details>
<summary>Compare with optimization disabled</summary>

The same column, expanded through all three models without simplification:

```bash
uv run extra inspect customer_profile --columns customer_name --optimize false
```

SQL output (CLI comments omitted; without optional dbt artifacts):

```sql
SELECT
  "customer_profile"."customer_name" AS "customer_name"
FROM (
  SELECT
    customer_id,
    first_name AS customer_name,
    last_name
  FROM (
    WITH customer_input AS (
      SELECT
        customer_id,
        first_name,
        last_name
      FROM (
        SELECT
          id AS customer_id,
          TRIM(first_name) AS first_name,
          last_name
        FROM main_raw.raw_customers
      ) AS "customers"
    )
    SELECT
      customer_id,
      first_name,
      last_name
    FROM customer_input
  ) AS "customer_details"
) AS "customer_profile";
```

The default optimized version removes the redundant wrappers, CTE and unused
outputs while preserving the name-cleaning expression. Both commands are read-only.

</details>

```text
customer_profile.customer_name
  ← customer_details.first_name
  ← stg_customers.first_name
  ← TRIM(jaffle_shop.customers.first_name)
```

<details>
<summary>See the three original model definitions</summary>

These teaching inputs deliberately contain a redundant CTE and unused columns.

**1. `stg_customers.sql`** reads customer records and cleans their names:

```sql
SELECT
    id AS customer_id,
    TRIM(first_name) AS first_name,
    last_name
FROM {{ source('jaffle_shop', 'customers') }}
```

**2. `customer_details.sql`** passes the customer attributes through a CTE:

```sql
WITH customer_input AS (
    SELECT customer_id, first_name, last_name
    FROM {{ ref('stg_customers') }}
)
SELECT customer_id, first_name, last_name
FROM customer_input
```

**3. `customer_profile.sql`** renames the first name:

```sql
SELECT
    customer_id,
    first_name AS customer_name,
    last_name
FROM {{ ref('customer_details') }}
```

</details>

Existing SQL aliases are preserved. Generated aliases use model/source names
instead of internal counters; long names use predictable abbreviations and a
stable fallback. See [alias naming](docs/guides/inspection-and-optimization.md#readable-aliases).
The path above summarizes lineage; it is not literal CLI output. A current
manifest may add database qualifiers and quoting to physical relation names.

### Preserve filters and grouping

Inspect an aggregate using the same simple command shape:

```bash
uv run extra inspect customer_revenue --columns revenue
```

The completed-order filter, decimal cast and customer grouping still affect
revenue, so they remain. The unused `order_count` output and redundant CTE and
selection wrapper are removed.

<details>
<summary>See the simplified revenue SQL</summary>

SQL output, with CLI comments omitted and without optional dbt artifacts:

```sql
SELECT
  order_totals.revenue + 0 AS "revenue"
FROM (
  SELECT
    SUM("orders".amount) AS revenue
  FROM (
    SELECT
      "demo_raw_orders".customer_id AS customer_id,
      CAST("demo_raw_orders".amount AS DECIMAL(12, 2)) AS amount
    FROM {{ ref('demo_raw_orders') }} AS "demo_raw_orders"
    WHERE
      "demo_raw_orders".status = 'completed'
  ) AS "orders"
  GROUP BY
    "orders".customer_id
) AS order_totals;
```

`revenue + 0` remains because removing it requires exact type evidence. The seed
reference remains a template when no current manifest resolves its physical name.

</details>

Inspection expands and simplifies definitions and resolves available relation
names by default. It changes no files and executes nothing. Necessary joins,
evaluation boundaries and row multiplicity are preserved; not every query can
be flattened. See the [inspection walkthrough](docs/guides/inspection-and-optimization.md)
for comparisons and the [CLI reference](docs/reference/cli.md#inspect) for options.

## Review and edit in Excel

Export a workbook without changing dbt source files:

```bash
uv run extra export --format xlsx --select customer_revenue
```

Open `extra/review/review.xlsx`. Model sheets follow project folders, with
**TABLE → STEP / OUTPUT → COLUMN** rows for models, CTEs, final queries and columns.
Sources use **SOURCE → TABLE → COLUMN** rows; macros, seeds and snapshots have
their own groups. Supported input cells are unlocked.

For a first edit, change **Description** on the `customer_revenue` TABLE row to:

```text
Completed-order revenue per customer, reviewed in Excel.
```

Save and close Excel, then preview the native YAML change:

```bash
uv run extra import extra/review/review.xlsx --preview
```

The proposal changes only the model description in `models/schema.yml`. To accept
it on your review branch or disposable copy:

```bash
uv run extra import extra/review/review.xlsx
git diff -- models/schema.yml
```

<details>
<summary>Supported workbook edits, constraints and expanded macro previews</summary>

The workbook also supports:

| Review content | Supported edits |
| --- | --- |
| Resource and final-output column metadata | Descriptions, types, tests, constraints, config, meta and other authored properties in existing YAML entries |
| Model SQL | Supported SELECT clauses and projection expressions, or full SQL through hidden `Authored SQL` cells—not both for the same model |
| Macros and SQL snapshots | Named macro bodies or supported authored SQL; macro docs and arguments through their properties |
| `Configuration` sheet | Authored model/seed/snapshot settings at their original package/folder scope in `dbt_project.yml` |

References display as shorthand such as `ref.orders` and `macro.round_money('amount')`;
import restores valid Jinja. Package/artifact-only resources, identities, lineage
and generated SQL are read-only. Keep hidden IDs and the baseline; do not add or
delete rows, rename resources or move them. Missing YAML entries are reported,
not created. Unchanged source files retain their bytes; changed YAML preserves
comments, quotes and unrelated entries.

If affected files change after export, re-export rather than bypassing the conflict.
For macro-generated column previews, use a separate expanded workbook:

```bash
uv run extra export --format xlsx --select macro_revenue --expand --output-dir extra/review-expanded
```

Generated expressions are read-only; edit authored SQL or the macro definition
instead. See the [review contract](docs/reference/catalogs.md) for scope restrictions,
formula rejection and baseline checks.

</details>

### Use CSV for flat reviews

```bash
uv run extra export --format csv --select customer_revenue --output-dir extra/review-csv
# Edit supported fields in resources.csv or columns.csv, retaining _baseline.json.
uv run extra import extra/review-csv --preview
```

Import needs the complete directory, including `_baseline.json`. CSV supports
authored SQL, resource/column metadata and supported simple root projection edits;
it is not the hierarchical XLSX scope editor. Treat untrusted CSV as text when
opening it in a spreadsheet to avoid formula interpretation.

### Export read-only JSON context

```bash
uv run extra export --format json --select customer_revenue orders demo_raw_orders --output-dir extra/review-json
```

`extra/review-json/review.json` contains authored SQL/properties, available config,
dependencies, inferred types and best-effort value lineage, plus coverage reasons
and provenance. The envelope includes `format_version: 1` and `source_of_truth: dbt`.
Include upstream resources explicitly; selecting a model does not automatically
export its dependencies. JSON is for analysis/integrations and cannot be imported.

## Optimize authored SQL

Optimization uses guarded static rewrites; it does not estimate warehouse costs or
guarantee faster queries. Inspection simplifies a read-only explanation;
`optimize` proposes edits to the authored model without inlining upstream models.

Preview changes to the actual model file, not a compiled copy:

```bash
uv run extra optimize --select gld_optimizer_constants --preview
```

The preview simplifies `1 + 2` to `3`, while preserving division whose type rules
are not proven.

<details>
<summary>See the original and proposed SQL</summary>

For this example, the SQL body starts as:

```sql
SELECT
  100 / 100 AS currency_scale,
  1 + 2 AS sample_value
```

The proposed SQL body is:

```sql
SELECT
  100 / 100 AS currency_scale,
  3 AS sample_value
```

The leading `config()` is also formatted, preserving its values. Division stays
unchanged rather than assuming arithmetic rules across dialects and types.
Optimization can simplify proven literals/predicates, prune supported projections,
qualify columns and simplify supported query structure when the required evidence
is available. Source optimization does not eliminate joins or infer uniqueness
from documentation.

</details>

<details>
<summary>Formatting and combined metadata proposals</summary>

Choose pretty or compact SQL/config layout, or include metadata proposals:

```bash
uv run extra optimize --select customer_revenue --format compact --preview
uv run extra optimize --select customer_revenue --enrich true --preview
```

</details>

Reports distinguish structural rewrites, qualification, formatting-only changes,
unchanged models and skips. Individual rules report applied, blocked or rolled-back
outcomes. A blocked rule need not prevent unrelated safe work; review retained
reasons rather than treating a changed-file count as complete optimization.

Remove `--preview` only to apply the reviewed changes. SQL and supported leading
config layout change in selected authored model files; compiled SQL is never edited.
See [optimizer safety](docs/guides/source-optimizer-safety.md) and
[partial optimization](docs/guides/partial-optimization.md) for rule guards,
schema requirements, rollback and diagnostic fields.

### Expand static local macros and templates

Source optimization preserves macro calls by default. Opt in
to replacing supported calls with SQL:

```bash
uv run extra optimize --select macro_revenue --expand true --preview
```

Before:

```sql
select customer_id, {{ round_money('revenue') }} as revenue
from {{ ref('customer_revenue') }}
```

Proposed source:

```sql
SELECT
  a.customer_id,
  ROUND(a.revenue, 2) AS revenue
FROM {{ ref('customer_revenue') }} AS a
```

Bounded static expansion supports local nested calls, multiple-column output,
literal-list loops, literal `set` statements and statically decidable branches.
It does not execute arbitrary Jinja, adapters, environment lookups or database
queries. Runtime-dependent calls remain explicit boundaries; unsupported source
expansion skips the whole model instead of writing a partial expansion.

`ref()`, `source()` and `config()` stay authored; upstream model definitions are
not inlined and macro files are unchanged. Top-level static templates remain
byte-for-byte intact unless source expansion is explicitly enabled. Inspection
and export expansion only generate read-only explanations/previews.

## Fill missing column metadata

```bash
uv run extra enrich --select customer_revenue --preview
```

The bundled example reports **4 missing properties inferred; 2 unresolved**.
The proposal adds three types and a passthrough description, without inventing
descriptions for transformed columns.

<details>
<summary>Compare the original YAML and metadata proposal</summary>

The existing `customer_revenue` YAML entry starts as:

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

The proposal fills three types and the unambiguous passthrough description:

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
        data_type: DECIMAL(38, 2)
      - name: order_count
        data_type: BIGINT
```

</details>

No descriptions are invented for transformed `revenue` or `order_count`.
Nonempty authored values are not overwritten. Only local SQL models with existing,
writable, nonversioned YAML entries are eligible; inferred columns may be added
inside those entries, but property files/model entries are not created. Existing
semantic models and metrics are preserved, not inferred.

Remove `--preview` to accept the proposal after review. If you applied the earlier
Excel edit, its reviewed model description stays unchanged. See
[metadata enrichment](docs/guides/metadata-enrichment.md) for skipped/unresolved
reasons and inference limits.

## Select resources

Export, optimize and enrich accept repeated `--select/-s` and `--exclude` options:

```bash
uv run extra export --select orders customer_revenue --preview
uv run extra export --select 'path:models/gld/**' --exclude macro_revenue --preview
uv run extra export --select 'tag:finance' --preview
uv run extra optimize --select model.jaffle_shop.customer_revenue --preview
```

Selectors match names, exact IDs or case-sensitive globs with `name:`, `id:`,
`path:`, `tag:`, `package:` and `resource_type:` prefixes. Multiple inclusions form
a union, then exclusions are removed. Explicit lists replace configured lists.
Optimize/enrich consider models only. dbt graph operators and intersections are
not supported. See [selector syntax](docs/reference/cli.md#select-resources).

## Validate a project

```bash
uv run extra validate
```

Validation checks resource discovery, local SQL-file Jinja structure, supported
static model SQL and reference cycles without changing files. Unavailable SQL
analysis is reported with reasons. This does not run dbt parsing, compilation,
builds, data tests or enforced-contract checks.

## Configure an existing project

With an installed CLI, run inside the directory containing `dbt_project.yml`:

```bash
cd path/to/your/dbt_project
extra --dialect snowflake inspect your_model --columns your_column
extra --dialect snowflake optimize --select your_model --preview
extra --dialect snowflake init --preview
```

Use your actual SQL dialect. From outside the project, put `--project-dir PATH`
before the command, or set `EXTRA_PROJECT_DIR`. Optional `extra_project.yaml`
settings live beside `dbt_project.yml`; SQL and business metadata stay in dbt files.
Project selection is explicit directory, then `EXTRA_PROJECT_DIR`, then
`DBT_PROJECT_DIR`, then the nearest ancestor containing `dbt_project.yml`.
Explicit directories must contain that file and do not fall back to another root.

`init` requires an existing dbt project. Remove `--preview` to create settings;
it refuses to overwrite an existing file and never creates a second model tree.
For the bundled DuckDB project, settings can include:

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
  output_dir: extra/review
  format: xlsx
  expand: false
  select:
    - 'path:models/gld/**'
  views:
    finance:
      select:
        - 'tag:finance'
optimization:
  format: pretty
  expand: false
  enrich: false
metadata:
  select:
    - customer_revenue
```

Preview the named view with `uv run extra export --view finance --preview`.
Views override base export settings; explicit flags override the view. Use your
project's dialect and selectors rather than copying the demo's assumptions.

Authored SQL/YAML are authoritative. A discoverable `target/manifest.json` supplies
optional identity/config/relation evidence; `--manifest PATH` chooses an explicit
existing manifest. Optional catalog evidence must be configured under
`dbt.artifacts.catalog`; it is not automatically loaded from `target/catalog.json`.
Artifacts do not replace authored SQL or verify warehouse state.

Global options go before the command. Relative project/manifest/import paths use
the current directory; configured paths and export destinations use the project
root. CLI values override settings, including replacing selection lists.

See the [existing-project guide](docs/guides/existing-dbt-project.md),
[configuration reference](docs/reference/configuration.md) and
[CLI options and selectors](docs/reference/cli.md).
The same CLI is available as `python -m dbt_extra`; use `extra --help`,
`extra COMMAND --help` and `extra --version` for discovery.

## Use the Python API

From `examples/jaffle_shop`, analyze resources, inspect selected columns and combine
SQL/metadata proposals without writing files:

```python
from dbt_extra import Project
from dbt_extra.analysis import catalog
from dbt_extra.enrichment import enrich
from dbt_extra.inspection import inspect, plan
from dbt_extra.optimization import optimize
from dbt_extra.sql.renderer import render

project = Project()  # Or Project("/path/to/project", dialect="duckdb").
document = catalog(project, project.select(["customer_revenue"]))
tree, parsed, issues = inspect(
    project, "customer_revenue", ["revenue"],
    boundaries=("orders",), compiled=False,
)
explanation = render(tree, parsed, project.dialect)
logical_plan = plan(tree, parsed, project.dialect)

changes, skipped = optimize(project, select=["customer_revenue"])
changes, report = enrich(project, select=["customer_revenue"], changes=changes)
print(changes.diffs())
changes.apply(preview=True)  # Check inputs; write nothing.
# changes.apply()  # Explicitly accept the proposed source edits.
```

`ChangeSet.changed()` exposes proposed bytes and `diffs()` exposes unified text
diffs. Inspect `skipped`, `issues`, enrichment `report` and
`changes.optimization_report` for coverage and rule outcomes. Create a fresh
`Project` after changing files; applying checks inputs against the loaded snapshot.
Workflow functions use Python defaults rather than automatically merging CLI
workflow settings; use `project.options(...)` to resolve configured options.

For SQL without a dbt project:

```python
from dbt_extra.sql.rewrites.engine import optimize_source

outcomes = []
sql = optimize_source("SELECT 1 + 2 AS k", "duckdb", outcomes=outcomes)
assert "3 AS k" in sql
```

`optimize_source` returns SQL without filesystem writes. An optional schema must
describe complete, ordered relation columns—not a partial documentation list.
The [Python API reference](docs/reference/python-api.md) also covers single-resource
analysis, validation, review export/import, errors and change application.

## Coverage and limitations

Analysis depends on the dialect, schema evidence and templates. Supported static
local macros can be analyzed without running Jinja; runtime-dependent logic stays
an explicit boundary. Inferred types and value lineage are best-effort.
The [SQL function reference](docs/reference/sql-functions/README.md) distinguishes
recognition, type inference and rewrite safety across eleven dialect catalogs.
The shared offline regression matrix covers DuckDB, PostgreSQL, Snowflake,
BigQuery, Spark, T-SQL, Fabric, Databricks, Redshift, Trino and Athena. Accepted
dialect names are SQLGlot names; cross-dialect parsing/rendering is not warehouse
execution certification or proof that every function can be inferred or rewritten.

Discovery follows configured dbt model/macro/seed/snapshot roots. SQL models have
the richest analysis; Python models and YAML-defined resources still expose
available metadata. Sources, seeds, snapshots, macro definitions/docs and
package/artifact resources remain visible with explicit analysis status/reasons.

Inspection explains definitions, not stored or incremental data. A logical plan
is not a warehouse execution plan, and an SQL rewrite is not a measured speedup.
Run dbt parsing, tests and builds independently. Writes have conflict checks and
rollback attempts, not crash-safe multi-file transactions or file locks.
Skipped models, unavailable analysis and unresolved properties can still return
exit code 0; inspect coverage as well as command success. Shared catalogs can
contain sensitive SQL/metadata; redact them and treat their contents as untrusted
data. dbt-extra includes no LLM client or autonomous agent.

See [compatibility](docs/compatibility.md),
[optimizer safety](docs/guides/source-optimizer-safety.md) and the
[production checklist](docs/guides/production-workflow.md) before adoption.

## Documentation and support

- [Documentation index](docs/index.md)
- [Native Jaffle Shop example](examples/jaffle_shop/README.md)
- [Five-step demo](docs/guides/five-step-demo.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [License](LICENSE)

For bugs, open an [issue](https://github.com/billybillysss/dbt-extra/issues) with a
minimal redacted reproduction and the coverage reason. Report vulnerabilities
through the [security policy](SECURITY.md), not a public issue.
