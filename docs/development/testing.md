# Testing

Run from the repository root after `uv sync --locked`:

```sh
uv run pytest
```

Pytest uses four workers by default. For easier debugging, run one file with
`uv run pytest -n 0 tests/test_documentation.py`. Tests that need DuckDB use the
development environment; a skipped optional dependency is not execution coverage.
Do not run dbt against a demo while pytest is running: read-only tests snapshot
the fixture tree, including any existing dbt logs and outputs.

## What the suite covers

- `workflows/test_dbt.py`: public dbt discovery, source rewriting, inspection,
  XLSX/CSV conflict-checked round trips, metadata inference and write rollback.
- `review/test_workbook.py`: hierarchical workbook layout, source bindings,
  scoped SQL edits, dbt configuration and unsupported workbook-layout rejection.
- `files/`: supported Python/C YAML backends and safe write failure behavior.
- `sql/`, `project/`, `analysis/`: focused shared primitives and dependency boundaries.
- `test_yaml_style.py`: block-style repository and documentation YAML.
- `test_documentation.py`: local Markdown paths/anchors, parsed JSON examples,
  documented SQL/YAML proposals, CLI option coverage, Python API examples and the
  temporary-copy five-step demo.
- `test_branding.py`: package/command identity, config/environment discovery,
  review envelopes, safe release automation and README references.
- `test_logo.py`: valid, accessible, self-contained SVG assets.

Keep tests focused on supported behavior and durable safety contracts. Migration
completion checks, retired names/options, and one-off branding or fixture-count
assertions do not belong in the ongoing suite. Compatibility checks remain when
they exercise a currently supported format or preserve authored user data.

Documentation checks are offline. They validate local targets and examples, not
the availability or content of external websites. Do not update example output
just to silence a failure without reviewing the semantic change.

## Executable integration checks

```sh
uv run extra --project-dir examples/jaffle_shop validate
uv run extra --project-dir examples/jaffle_shop export --preview
uv run extra --project-dir examples/jaffle_shop optimize --preview
uv run dbt build --project-dir examples/jaffle_shop --profiles-dir examples/jaffle_shop
uv run dbt docs generate --project-dir examples/jaffle_shop --profiles-dir examples/jaffle_shop
```

Jaffle Shop is the shared native dbt integration fixture. Its `dbt build` runs
seeds, models, snapshots and tests together in the in-memory DuckDB target.
These checks do not replace adapter-specific production acceptance tests.

## Self-contained optimizer regressions

`tests/synthetic.py` generates a separate dbt project with CSV seeds, passthrough,
aggregate/window/shared models, static/runtime Jinja boundaries, a wide feature
model and temporal prior-event counts. No originating project or credentials are
needed. The temporal fixture covers inclusive lower/exclusive upper time bounds,
strictly earlier evidence and multiple findings per event without count inflation.

```sh
uv run pytest tests/sql/test_partial_optimization.py tests/sql/test_static_jinja.py tests/workflows/test_synthetic_optimization.py
uv run python -m scripts.benchmark_inspection --repeats 4 12 24
```

To create an inspectable project outside the repository's examples:

```sh
uv run python -c "from pathlib import Path; from tests.synthetic import synthetic_project; synthetic_project(Path('extra/synthetic'))"
uv run extra --project-dir extra/synthetic inspect fact_metrics --columns selected_metric --compile false
```

The shared `tests/semantics.py` oracle compares duplicate-aware row multisets,
output labels/order and exact engine types. An outer ORDER BY requires ordered
rows, not a Counter. Success is required by default: expected failures declare
an exception class and reason, and both queries must match that error signature.
Two arbitrary failures are not equivalence. Deliberately broken candidates test
the oracle itself. Rule-failure injection checks rollback and unavailable dependent
capabilities. CI separately tests SQLGlot 30.29.0 and fresh dependency resolution,
including source rewrites, effect safety and independent Jinja checks.

`tests/sql/test_generated_optimization.py` uses fixed random seeds, query
constants and duplicate/NULL/extreme integer data, with either/both inputs empty.
It exercises rule interactions in source and inspection paths; positive controls
assert that rules actually apply, not just that unchanged SQL still executes.
This is reproducible generated coverage, not exhaustive fuzzing or a proof.

`tests/sql/test_jinja_execution.py` compares against real Jinja rather than using
the production interpreter on both sides. The opt-in real dbt test below builds
eight temporary models before and after applying optimizer changes, in both macro
modes, and compares compiled queries plus materialized tables. It does not mutate
the examples or require external credentials:

```sh
DBT_EXTRA_DBT_TESTS=1 uv run pytest -n 0 tests/workflows/test_optimizer_dbt_execution.py
```

The main integration CI lane runs this separately from the demo preview/build.

For Spark 4.2.1, install Java 21 and use an isolated Python 3.13 environment. This runs
only local JVM SQL over synthetic VALUES; no warehouse, credentials or Python
worker is needed:

```sh
env -u SPARK_HOME DBT_EXTRA_SPARK_TESTS=1 SPARK_LOCAL_IP=127.0.0.1 uv run --no-project --python 3.13 --with-editable . --with pytest --with pytest-xdist --with duckdb --with pyspark==4.2.1 python -m pytest -n 0 tests/sql/test_spark_optimization.py
```

The environment-variable syntax above is POSIX shell syntax; set the two variables
with your shell's equivalent on Windows. Without opt-in these tests are skipped,
not counted as Spark execution coverage. The dedicated CI lane executes them with
ANSI mode both enabled and disabled. DuckDB success alone is not Spark proof.
Point JAVA_HOME at Java 21 and unset an inherited SPARK_HOME so PySpark launches
its bundled Spark, not an unrelated local installation. The fixture verifies the
running Spark version against the installed PySpark version and the 4.2 target.
Positive controls exercise normalization, pushdown, join reordering, factoring,
typed membership and complementary UNION scans; native Spark null predicates and
mixed-key conversion boundaries are executed without translating to DuckDB.

For PostgreSQL, use a disposable PostgreSQL 16 instance and install the optional
driver. The fixture creates only session-local TEMP tables, but still use a
dedicated test database/account, never production credentials:

```sh
uv pip install "psycopg[binary]>=3.2,<4"
DBT_EXTRA_POSTGRES_DSN=postgresql://optimizer:optimizer@localhost:5432/optimizer_tests uv run --no-sync pytest -n 0 tests/sql/test_postgres_optimization.py
```

The DSN is supplied only at execution time; do not commit real secrets. CI uses an
ephemeral PostgreSQL 16 service. Without a DSN these tests skip; with opt-in, missing
drivers or connection failures fail the lane. PostgreSQL membership rewriting
remains disabled. Cloud dialects still have offline tests only, not credentials or
remote execution coverage. A configured CI lane is not a claim that it has passed.

## Distribution checks

```sh
uv build
uv venv .venv-package-smoke
uv pip install --python .venv-package-smoke dist/dbt_extra-0.2.2-py3-none-any.whl
```

Run the following with **that environment's Python**, not `uv run` (which would
select the checkout environment):

```sh
# POSIX
.venv-package-smoke/bin/python scripts/smoke_distribution.py
```

```powershell
# Windows PowerShell
.venv-package-smoke/Scripts/python.exe scripts/smoke_distribution.py
```

The script checks wheel/sdist license metadata and source documentation/fixtures,
then invokes the installed CLI from a temporary directory to initialize, validate
and export native JSON/XLSX and preview import. Repeat after installing the source archive to test sdist
installation too. The versioned wheel path above must match the version built.
The validation workflow uses an isolated environment and does not publish packages.
The [release workflow](https://github.com/billybillysss/dbt-extra/blob/HEAD/.github/workflows/release.yml)
calls validation before building and publishing to PyPI on `v*` tags or manual
dispatch. Normal pushes and pull requests run validation without publishing.

The package job also installs pytest and DuckDB into the wheel environment and
runs the full suite against freshly resolved runtime dependencies. This is
separate from the locked checkout tests: a simple initialization smoke test does
not exercise SQL optimization or prove the entire dependency range works.
