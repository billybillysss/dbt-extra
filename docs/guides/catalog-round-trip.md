# Review and import an editable catalog

Start with a description-only edit. It demonstrates the review loop without
changing business logic. Install from the [getting-started guide](../getting-started.md)
first, then run these commands from the repository root.

## 1. Export one model

```bash
uv run --locked extra --project-dir examples/jaffle_shop export --format xlsx --select customer_revenue
```

Open `examples/jaffle_shop/extra_review/review.xlsx` in Excel. Review files can
contain sensitive SQL and metadata; this demo uses only bundled fixtures.

## 2. Edit a supported description

Find `customer_revenue` in the model sheet for `models/gld`. Rows form
`TABLE → STEP / OUTPUT → COLUMN`; expand the outline if necessary.
On the **TABLE** row, change **Description** to:

```text
Completed-order revenue per customer, reviewed in Excel.
```

Leave IDs, names, paths, SQL and other cells unchanged. Do not add/delete rows or
remove hidden sheets. Save the workbook and **close Excel** to release file locks.

## 3. Preview the source diff

```bash
uv run --locked extra --project-dir examples/jaffle_shop import examples/jaffle_shop/extra_review/review.xlsx --preview
```

Expect a description change in `examples/jaffle_shop/models/schema.yml` and no
SQL changes. Preview writes nothing. If no supported cell changed, a no-op import
has no file changes. If an affected source changed after export, stop and re-export
rather than bypassing the stale-export check.

## 4. Apply only if you want the change

The next command **changes the bundled project's YAML**. Use a disposable checkout
or a branch, and run it only after reviewing the preview:

```bash
uv run --locked extra --project-dir examples/jaffle_shop import examples/jaffle_shop/extra_review/review.xlsx
git diff -- examples/jaffle_shop/models/schema.yml
```

Review the Git diff and run your independent dbt checks before accepting a real
project change. Import wanted edits before refreshing the workbook; once applied,
export a fresh workbook before starting another review.

## Use your own project

With an installed CLI, run from your dbt project directory (configure its dialect
or provide `--dialect` if it cannot be determined):

```bash
extra export --format xlsx
extra import extra_review/review.xlsx --preview
extra import extra_review/review.xlsx
```

## Editing boundaries

Edit supported input cells only. IDs, names, paths, statuses and lineage are
read-only. Resource/column `properties` JSON holds tests, constraints and configs.
Choose full SQL or supported expression edits, not both for the same model.

CSV import needs the whole directory, including `_baseline.json`. JSON is
read-only. No-op import changes nothing; row additions/deletions, renames and
moves are unsupported. Exported inferred-column rows can gain authored metadata.

Changed affected files cause a stale-export conflict. Re-export instead of
overwriting concurrent work. Preview source diffs and run dbt checks. See the
[complete contract](../reference/catalogs.md).
