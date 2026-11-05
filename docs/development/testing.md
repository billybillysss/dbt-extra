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
  scoped SQL edits, dbt configuration and flat-workbook compatibility.
- `files/`: supported Python/C YAML backends and safe write failure behavior.
- `sql/`, `project/`, `analysis/`: focused shared primitives and dependency boundaries.
- `test_yaml_style.py`: block-style repository and documentation YAML.
- `test_documentation.py`: local Markdown paths/anchors, parsed JSON examples,
  dbt README workflows and Python API examples.
- `test_branding.py`: package/command identity, config/environment discovery,
  review envelopes, safe release automation and README references.
- `test_logo.py`: accessible SVGs and exact preservation of the supplied Modular
  joint icon's paths and palette across light/dark variants.

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

The handwritten `analytics/` fixture additionally runs `dbt parse`, `dbt seed`,
`dbt build` and `dbt test` with `--project-dir analytics --profiles-dir analytics`.
These checks do not replace adapter-specific production acceptance tests.

## Distribution checks

```sh
uv build
uv venv .venv-package-smoke
uv pip install --python .venv-package-smoke dist/dbt_extra-0.1.0-py3-none-any.whl
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
The manual [release-candidate workflow](https://github.com/billybillysss/dbt-extra/blob/HEAD/.github/workflows/release.yml)
also calls validation and builds artifacts, but never publishes; see [releasing](releasing.md).

The package job also installs pytest and DuckDB into the wheel environment and
runs the full suite against freshly resolved runtime dependencies. This is
separate from the locked checkout tests: a simple initialization smoke test does
not exercise SQL optimization or prove the entire dependency range works.
