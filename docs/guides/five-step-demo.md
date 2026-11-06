# Five-step demo

**Three models → readable SQL → optimizer diff → Excel edit → YAML diff.**

This demonstration shows dbt-extra as a local dbt development companion, not a
replacement for dbt or a warehouse performance tuner. All inputs come from the
bundled [Jaffle Shop project](../../examples/jaffle_shop/README.md).

## Run the complete demo

From a source checkout, with Python 3.11+ and uv:

```bash
uv run --locked --no-dev python -m scripts.demo_review
```

Source access is required while the repository is private. The script copies the
example to a temporary directory, invokes the real CLI, edits a workbook with
openpyxl, and prints SQL and YAML previews. No Excel application, dbt installation,
warehouse credentials or network access is needed after dependencies are installed.
`--no-dev` installs only runtime dependencies, without the dbt development adapter.
It checks that inspection and previews write nothing and that original project
files remain unchanged, then removes its temporary files. To choose a temporary
parent directory, add `--temp-dir PATH` to the script command.

The workbook edit is automated for reproducibility; it is the same supported cell
you can edit manually in Excel. This script does not apply either source proposal.
It is a checkout utility, not an installed `extra` command.

## 1. Follow a column through three models

The script first runs the equivalent of this command from the copied project:

```bash
extra inspect customer_profile --columns customer_name --optimize false
```

`customer_profile.customer_name` follows `customer_details.first_name` and
`stg_customers.first_name` back to `TRIM(first_name)` on the customer source.
With simplification disabled, the wrappers and unused outputs remain visible.

## 2. Show only the relevant logic

```bash
extra inspect customer_profile --columns customer_name
```

SQL output, with CLI comments omitted and without optional artifacts:

```sql
SELECT
  TRIM("customers".first_name) AS "customer_name"
FROM main_raw.raw_customers AS "customers";
```

The unused columns, redundant CTE and wrappers disappear; the cleaning expression
remains. This is a read-only explanation across model definitions, not a source
rewrite, runtime-equivalence proof or description of stored warehouse data.

## 3. Preview an authored-SQL optimization

```bash
extra optimize --select gld_optimizer_projections --preview
```

The model's SQL body starts as:

```sql
WITH projected AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.status AS unused_status
    FROM {{ ref('slv_orders') }} AS o
),
normalized AS (
    SELECT p.order_id, p.customer_id
    FROM projected AS p
),
unused AS (
    SELECT 9 AS ignored
)
SELECT n.order_id, n.customer_id
FROM normalized AS n
WHERE n.customer_id > 0 AND TRUE
```

Proposed SQL body:

```sql
SELECT
  o.order_id,
  o.customer_id
FROM {{ ref('slv_orders') }} AS o
WHERE
  o.customer_id > 0
```

The leading `config()` is also formatted, with its values preserved. The dbt
reference stays authored: unlike inspection, source optimization does not inline
upstream models. Rules depend on available schema evidence and supported semantics.
These are guarded static rewrites, not measured speedups or warehouse cost estimates.
See [optimizer safety](source-optimizer-safety.md) for boundaries.

## 4. Edit a supported Excel cell

```bash
extra export --format xlsx --select customer_revenue
```

The script opens `extra/review/review.xlsx` and sets **Description** on the
`customer_revenue` **TABLE** row to:

```text
Completed-order revenue per customer, reviewed in Excel.
```

To do this manually, save and close Excel before importing. Keep hidden IDs and
the baseline intact; do not add/delete rows or rename resources. See the
[review walkthrough](catalog-round-trip.md) for supported SQL and metadata edits.

## 5. Review the YAML proposal

```bash
extra import extra/review/review.xlsx --preview
```

The diff targets the model description in `models/schema.yml`, not a generated
catalog or replacement model tree. Preview leaves SQL/YAML unchanged. The export
and edited workbook exist only inside the temporary copy and are removed on exit.

For real projects, review diffs on a branch and run dbt parsing, tests and builds
independently before accepting changes. If watched source inputs change after
export, re-export instead of bypassing the baseline conflict.
