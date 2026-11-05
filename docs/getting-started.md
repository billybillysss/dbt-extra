# Getting started

Start with the bundled project, then try one model from your own dbt project.
extra runs offline: no warehouse credentials or dbt compilation are needed.

## Install from this checkout

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/), then:

```bash
git clone https://github.com/billybillysss/dbt-extra.git
cd dbt-extra
uv sync --locked
uv run extra --version
```

This is the private `0.2.0` preview; cloning requires repository access.
The executable is `extra`; Python imports use `dbt_extra`.
See [compatibility](compatibility.md) for supported versions and limitations.

Prefer pip? From the cloned repository, create and activate a virtual environment
with Python 3.11+, then run `python -m pip install .`. Replace `uv run extra`
with `extra` in the commands below. dbt execution is optional and requires your own
dbt/adapter installation; `uv sync --locked` includes the demo's development dependencies.

## Inspect your first column

Enter the dbt project once; uv finds the checkout's environment from here:

```bash
cd examples/jaffle_shop
uv run extra inspect customer_revenue --columns revenue --compile false
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
uv run extra inspect customer_revenue --columns revenue --from orders --compile false
uv run extra inspect customer_revenue --columns revenue --view plan --compile false
```

With `--from orders`, inspection stops at `orders`; its internal filter is no
longer expanded. None of these commands changes source files or executes SQL.
`--compile false` keeps dbt relation templates visible; the default resolves
available physical relation names offline, not through `dbt compile`.

## Review a model in Excel

```bash
uv run extra export --format xlsx --select customer_revenue
```

Open `extra/review/review.xlsx`. Follow the
[round-trip walkthrough](guides/catalog-round-trip.md) to edit a description and
preview the YAML diff. Export creates review files, not new dbt models.

## Use an existing dbt project

No generated-model directory or new model language is needed. With an installed CLI:

```bash
cd /path/to/project
extra --dialect duckdb validate
extra --dialect duckdb inspect your_model --columns your_column
extra --dialect duckdb export --format xlsx --select your_model
extra --dialect duckdb import extra/review/review.xlsx --preview
```

Use your actual dialect, not necessarily DuckDB. Optional manifest/catalog
artifacts supply evidence, never source rewriting input. Without SQL evidence,
metadata still exports with explicit analysis-availability reasons.
Alternatively, from this checkout, run
`uv run extra --project-dir /path/to/project --dialect duckdb validate`.
Project selection is `--project-dir` > `EXTRA_PROJECT_DIR` > nearest
`dbt_project.yml` upward. Optional settings live beside that file; explicit
directories do not search parents. Setting the environment does not change the
current directory: CLI input paths remain relative to it, while export destinations
and configured paths are relative to the project root.

## Optional settings

`extra init --preview` inside your project (or
`extra --project-dir /path/to/project init --preview`) shows an optional settings file without
creating it; remove `--preview` to write it. Initialization requires an existing
`dbt_project.yml`, refuses overwrites, and does not create a second model tree.
Add your dialect to `analysis.dialect` if no manifest supplies one.

CLI values replace matching configured values, including lists. See
[configuration](reference/configuration.md) and the [CLI](reference/cli.md).

## Review before applying

Export XLSX/CSV, edit only supported cells, then import with `--preview`.
`optimize --preview` shows actual authored SQL diffs; `enrich --preview` shows
missing metadata proposals. Preview never writes files.
Run dbt parsing/tests/builds independently before accepting changes. See
[the review contract](reference/catalogs.md) for limitations and conflict handling.
