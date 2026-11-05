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
uv run --locked extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --compile false
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

> **Private preview · 0.1.0:** install from this checkout with repository access.
> The executable is `extra`; Python imports use `dbt_extra`.
> [Migrating from slbt](docs/guides/migrating-from-slbt.md).

## Pick your workflow

| You want to… | Use dbt-extra to… |
| --- | --- |
| Understand one output column | Follow supported upstream SQL while retaining joins, filters, grouping and row multiplicity. |
| Review SQL and metadata together | Export a folder-grouped XLSX workbook or CSV, edit supported cells, and preview diffs back to dbt files. |
| Review an AI-proposed change | Export read-only JSON with SQL, dependencies, column lineage and explicit coverage reasons for an external assistant. |
| Clean up authored SQL | Preview conservative rewrites that preserve dbt calls; unsafe or opaque cases are skipped with reasons. |
| Fill missing documentation | Infer available types and unambiguous passthrough descriptions without overwriting authored metadata. |

### Review in Excel, apply through a diff

```bash
uv run --locked extra --project-dir examples/jaffle_shop export --format xlsx --select customer_revenue
# Edit supported cells in examples/jaffle_shop/extra_review/review.xlsx, then close Excel.
uv run --locked extra --project-dir examples/jaffle_shop import examples/jaffle_shop/extra_review/review.xlsx --preview
```

The workbook groups `TABLE → STEP / OUTPUT → COLUMN` rows. Supported edits patch
the original SQL/YAML; stale exports are rejected, YAML comments are preserved,
and unchanged files keep their bytes. Preview writes nothing. Follow the
[round-trip walkthrough](docs/guides/catalog-round-trip.md) before applying edits.

### Preview SQL cleanup and metadata proposals

```bash
uv run --locked extra --project-dir examples/jaffle_shop optimize --select customer_revenue --preview
uv run --locked extra --project-dir examples/jaffle_shop enrich --select customer_revenue --preview
```

For more visible before/after SQL rewrites, try the
[14 focused optimizer demos](examples/jaffle_shop/models/gld/optimization/README.md).
Logical cleanup is **not** a measured warehouse speedup.

## Use your existing dbt project

Point `--project-dir` at your project and supply its actual SQL dialect:

```bash
uv run --locked extra --project-dir path/to/your/dbt_project --dialect snowflake inspect your_model --columns your_column
```

dbt SQL and property YAML remain the source of truth. No initialization is
required. Optional `extra_project.yaml` stores tool settings only:

```yaml
version: 2
analysis:
  dialect: duckdb
export:
  format: xlsx
  output_dir: extra_review
  select:
    - 'path:models/gld/**'
optimization:
  format: pretty
  preserve_macros: true
```

Explicit CLI values replace configured values, including lists. `--preview`
(`--dry-run`) writes no files. Without it, writing commands apply their
[documented writes](docs/reference/cli.md). See the
[existing-project guide](docs/guides/existing-dbt-project.md) for artifact and dialect setup.

## Python API

```python
from dbt_extra import Project
from dbt_extra.analysis import catalog
from dbt_extra.optimization import optimize

project = Project("examples/jaffle_shop")
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
  remain opaque. Generated SQL never replaces an authored macro call.
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
