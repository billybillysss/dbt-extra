# Project configuration

`extra_project.yaml` is **optional tool settings**, not transformation definitions.
dbt's `dbt_project.yml` owns model/macro/snapshot/seed paths and execution settings.

```yaml
version: 2
dbt:
  project_dir: .
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
  output_dir: extra_review
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
  preserve_macros: true
  enrich: false
  select:
    - 'path:models/gld/**'
metadata:
  new_properties_file: models/_extra_properties.yml
  select:
    - 'path:models/gld/**'
```

Remove the optional `dbt.artifacts` entries if those files do not exist. Explicitly
configured artifact paths must exist. Otherwise `target/manifest.json` is used
when present, without being required. No artifact or compilation is necessary
when SQL/dialect/schema evidence is available in authored files.

## Resolution and precedence

1. `--project-dir` / exact `EXTRA_PROJECT_DIR` resolution selects settings.
2. Otherwise search upward for `extra_project.yaml`.
3. With no settings, a native `dbt_project.yml` is discovered upward.
4. `dbt.project_dir`, when set, is relative to the settings directory.

Precedence: **explicit CLI value > tool settings > discoverable dbt evidence >
default**. Explicit lists replace corresponding configured lists; they are not
unioned. Omitted CLI options do not supply parser defaults that erase settings.
For example, configured XLSX plus `select: [orders]` followed by
`extra export --select customers` exports customers as XLSX, not both selections.

`export.default_view` can name an entry in `export.views`; explicit `--view`
selects another. A view overrides format/select/exclude/expand; explicit flags then
override that view. Supported SQL dialects are SQLGlot dialect names. `auto`
uses the manifest adapter; without a dialect, metadata review is possible but
SQL operations require an explicit choice rather than guessing Spark.

## Defaults and boundaries

Default export: XLSX under `extra_review`, static macro expansion false. Set
`export.expand: true` (or a named view's `expand: true`) for generated previews.
Inspection: expand, optimize, and compile true (offline physical relation names),
no explicit boundaries. Optimization: pretty, preserve macros true, no enrichment.
Metadata: fill missing values only; create properties beside their original model.

Keep analysis, inspection, export, optimization and metadata tool settings here.
Resource paths belong in `dbt_project.yml`; business metadata belongs in dbt
properties. Credentials and execution profiles stay in dbt's own configuration.
Unknown settings are errors.
