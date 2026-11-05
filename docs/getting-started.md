# Getting started

Start with the bundled project, then try one model from your own dbt project.
extra runs offline: no warehouse credentials or dbt compilation are needed.

## Install from this checkout

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/), then:

```bash
git clone https://github.com/billybillysss/dbt-extra.git
cd dbt-extra
uv sync --locked
uv run --locked extra --version
```

This is the private `0.1.0` preview; cloning requires repository access.
The executable is `extra`; Python imports use `dbt_extra`.
See [compatibility](compatibility.md) and the [migration guide](guides/migrating-from-slbt.md).

Prefer pip? From the cloned repository, create and activate a virtual environment
with Python 3.11+, then run `python -m pip install .`. Replace `uv run --locked extra`
with `extra` in the commands below. dbt execution is optional and requires your own
dbt/adapter installation; `uv sync --locked` includes the demo's development dependencies.

## Inspect your first column

Run from the repository root:

```bash
uv run --locked extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --compile false
```

The SQL explains `customer_revenue → orders → demo_raw_orders`. Look for:

- `status = 'completed'`: upstream row filtering still matters to revenue.
- `DECIMAL(12, 2)`: the authored cast remains visible.
- `SUM` and `GROUP BY customer_id`: selecting one output does not discard its grain.
- A seed-input boundary: dbt-extra explains definitions, not seed execution or stored data.

`revenue + 0` is retained; a decimal expression cannot be assumed type-equivalent
to the same expression without addition. Unknowns and conservative skips are
information to review, not permission to guess.

Compare a bounded explanation and a logical plan:

```bash
uv run --locked extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --from orders --compile false
uv run --locked extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --view plan --compile false
```

With `--from orders`, inspection stops at `orders`; its internal filter is no
longer expanded. None of these commands changes source files or executes SQL.
`--compile false` keeps dbt relation templates visible; the default resolves
available physical relation names offline, not through `dbt compile`.

## Review a model in Excel

```bash
uv run --locked extra --project-dir examples/jaffle_shop export --format xlsx --select customer_revenue
```

Open `examples/jaffle_shop/extra_review/review.xlsx`. Follow the
[round-trip walkthrough](guides/catalog-round-trip.md) to edit a description and
preview the YAML diff. Export creates review files, not new dbt models.

## Use an existing dbt project

No generated-model directory or new model language is needed:

```bash
uv run --locked extra --project-dir path/to/project --dialect duckdb validate
uv run --locked extra --project-dir path/to/project --dialect duckdb inspect your_model --columns your_column
uv run --locked extra --project-dir path/to/project --dialect duckdb export --format xlsx --select your_model
uv run --locked extra --project-dir path/to/project --dialect duckdb import path/to/project/extra_review/review.xlsx --preview
```

Use your actual dialect, not necessarily DuckDB. Optional manifest/catalog
artifacts supply evidence, never source rewriting input. Without SQL evidence,
metadata still exports with explicit analysis-availability reasons.
Keep running `uv run` from this checkout; `--project-dir` can point to an absolute
path elsewhere. For an installed CLI, run `dbt-extra` directly from any directory.

## Optional settings

`extra init path/to/project --preview` shows an optional settings file without
creating it; remove `--preview` to write it. Initialization requires an existing
`dbt_project.yml`, refuses overwrites, and does not create a second model tree.
Add your dialect to `analysis.dialect` if no manifest supplies one.

CLI values replace matching configured values, including lists. See
[configuration](reference/configuration.md) and the [CLI](reference/cli.md).

## Review before applying

Export XLSX/CSV, edit only supported cells, then import with `--preview`.
`optimize --preview` shows actual authored SQL diffs; `enrich --preview` shows
missing metadata proposals. Preview and its `--dry-run` alias never write files.
Run dbt parsing/tests/builds independently before accepting changes. See
[the review contract](reference/catalogs.md) for limitations and conflict handling.
