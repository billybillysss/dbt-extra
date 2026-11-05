# Project configuration

`extra_project.yaml` is **optional tool settings**, not transformation definitions.
dbt's `dbt_project.yml` owns model/macro/snapshot/seed paths and execution settings.

```yaml
version: 2
dbt:
  artifacts:
    manifest: target/manifest.json
    catalog: target/catalog.json
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
  exclude: []
  views:
    finance:
      format: csv
      select:
        - 'tag:finance'
optimization:
  format: pretty
  expand: false
  enrich: false
  select:
    - 'path:models/gld/**'
metadata:
  select:
    - 'path:models/gld/**'
```

Remove the optional `dbt.artifacts` entries if those files do not exist. Explicitly
configured artifact paths must exist. Otherwise `target/manifest.json` is used
when present, without being required. No artifact or compilation is necessary
when SQL/dialect/schema evidence is available in authored files.

## Resolution and precedence

There is one project root: the directory containing `dbt_project.yml`.

1. Explicit `--project-dir PATH` selects that root.
2. Otherwise the exact `EXTRA_PROJECT_DIR` environment variable selects it.
3. Otherwise search upward from the current directory for the nearest
   `dbt_project.yml`.

Explicit directories must contain `dbt_project.yml`; they do not search parents.
Load optional `extra_project.yaml` only beside the selected `dbt_project.yml`.
Settings in parent directories do not override a nearer dbt project.
`Project(directory)` in Python follows the same rules; `Project()` discovers the
root or uses the environment. `init` uses the same root and takes no positional
directory: use `extra --project-dir PATH init`, not `extra init PATH`.

**Migration:** `dbt.project_dir` is no longer supported and produces an error.
Move `extra_project.yaml` beside the intended `dbt_project.yml`, remove
`dbt.project_dir`, and select that root. External settings directories are no
longer supported. No `DBT_PROJECT_DIR` or alternative environment alias is read.

### Relative paths

| Path | Relative to |
| --- | --- |
| `--project-dir`, `EXTRA_PROJECT_DIR`, Python `Project(directory)` | Current working directory |
| CLI `--manifest PATH`, `import PATH` | Current working directory |
| Configured `dbt.artifacts.*`, `export.output_dir`, dbt resource paths | Project root |
| CLI export `--output-dir` / `--path` | Project root |

Absolute paths remain absolute (resource paths must still stay within the project).
No existence-based guessing changes these rules. Setting `EXTRA_PROJECT_DIR` does
not change the working directory or rebase import paths.

For short everyday commands, `cd` into the dbt project and run `extra inspect`,
`extra export`, or `extra import extra/review/review.xlsx --preview` with the
appropriate model/options. From this repository checkout, use `uv run extra`.

For other options, precedence is **explicit CLI value > tool settings > discoverable dbt evidence >
default**. Explicit lists replace corresponding configured lists; they are not
unioned. Omitted CLI options do not supply parser defaults that erase settings.
For example, configured XLSX plus `select: [orders]` followed by
`extra export --select customers` exports customers as XLSX, not both selections.

`export.default_view` can name an entry in `export.views`; explicit `--view`
selects another. A view overrides format/select/exclude/expand; explicit flags then
override that view. Supported SQL dialects are SQLGlot dialect names. `auto`
uses the manifest adapter, translating `fabricspark` to `spark` and `sqlserver`
to `tsql`; `fabric` retains its dedicated SQLGlot `fabric` dialect. Explicit
choices use SQLGlot names, not adapter aliases. Without a dialect, metadata review
is possible but SQL operations require an explicit choice rather than guessing
Spark. See [dialect coverage](../compatibility.md#sql-dialects).

## Defaults and boundaries

Default export: XLSX under `extra/review/`, static macro expansion false. Set
`export.expand: true` (or a named view's `expand: true`) for generated previews.
Inspection: expand, optimize, and compile true (offline physical relation names),
no explicit boundaries. Optimization: pretty, expand false (preserve macros), no enrichment.
Set `optimization.expand: true` to write supported static local macros as SQL;
explicit `optimize --expand false` overrides that setting. Relation/config calls
remain authored. Unlike inspection/export expansion, optimization expansion can
change source files; use `--preview` to review without writing.
Metadata: fill missing values only in existing dbt YAML resource entries. Missing
entries are skipped with a reason; no properties files are created. Analysis and
inference stay in memory until an explicit export or accepted source edit.

Keep analysis, inspection, export, optimization and metadata tool settings here.
Resource paths belong in `dbt_project.yml`; business metadata belongs in dbt
properties. Credentials and execution profiles stay in dbt's own configuration.
Unknown settings are errors.
