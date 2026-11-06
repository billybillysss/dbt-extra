# Project configuration

`extra_project.yaml` is **optional tool settings**, not transformation definitions.
dbt's `dbt_project.yml` owns model/macro/snapshot/seed paths and execution settings.

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
  exclude: []
  views:
    finance:
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
    - customer_revenue
```

This example uses the bundled Jaffle Shop project. Replace its dialect and
selectors for your project. No artifact or compilation is necessary when the
required SQL, dialect and schema evidence is available in authored files.

## Settings reference

All sections are optional. Unknown keys are errors; Boolean values must be YAML
`true` or `false`, and selection/boundary values must be lists of nonempty strings.

| Key | Default | Meaning |
| --- | --- | --- |
| `version` | `2` | Tool settings version; only 2 is accepted |
| `dbt.artifacts.manifest` | `target/manifest.json`, if present | Manifest evidence; an explicitly configured path must exist |
| `dbt.artifacts.catalog` | None | Optional catalog evidence; a configured path must exist; not discovered automatically |
| `analysis.dialect` | `auto` | SQLGlot dialect, or manifest adapter autodetection |
| `inspection.expand` | `true` | Expand supported upstream models and static local macros |
| `inspection.optimize` | `true` | Simplify inspection SQL |
| `inspection.compile` | `true` | Resolve available physical relation names offline |
| `inspection.boundaries` | `[]` | Upstream model names/IDs at which inspection stops |
| `export.output_dir` | `extra/review` | Review destination |
| `export.format` | `xlsx` | `xlsx`, `csv` or read-only `json` |
| `export.expand` | `false` | Show generated, read-only static macro previews |
| `export.select`, `export.exclude` | All resources, no exclusions | Export selectors |
| `export.default_view` | None | Named view to use when `--view` is omitted |
| `export.views.NAME` | None | Mapping with optional `format`, `select`, `exclude`, `expand` overrides |
| `optimization.format` | `pretty` | `pretty` or `compact` SQL/config layout |
| `optimization.expand` | `false` | Permit static macro/template replacement in source SQL |
| `optimization.enrich` | `false` | Include missing-metadata proposals for the optimization selection |
| `optimization.select`, `optimization.exclude` | All models, no exclusions | SQL optimization selectors |
| `metadata.select`, `metadata.exclude` | All models, no exclusions | Standalone enrichment selectors |

To load artifacts explicitly, add:

```yaml
dbt:
  artifacts:
    manifest: target/manifest.json
    catalog: target/catalog.json
```

These paths must exist. The manifest supplies identity, configuration and relation
evidence, not compiled SQL for rewriting. Artifacts do not verify current
warehouse state; use the intended target's artifacts and review freshness warnings.

## Resolution and precedence

There is one project root: the directory containing `dbt_project.yml`.

1. Explicit `--project-dir PATH` selects that root.
2. Otherwise the exact `EXTRA_PROJECT_DIR` environment variable selects it.
3. Otherwise the exact `DBT_PROJECT_DIR` environment variable selects it.
4. Otherwise search upward from the current directory for the nearest
   `dbt_project.yml`.

Explicit directories (including environment values) must contain `dbt_project.yml`;
they do not search parents or fall back to lower-priority selections.
Load optional `extra_project.yaml` only beside the selected `dbt_project.yml`.
Settings in parent directories do not override a nearer dbt project.
`Project(directory)` in Python follows the same rules; `Project()` discovers the
root or uses the environment. `init` uses the same root and takes no positional
directory: use `extra --project-dir PATH init`, not `extra init PATH`.

**Migration:** `dbt.project_dir` is no longer supported and produces an error.
Move `extra_project.yaml` beside the intended `dbt_project.yml`, remove
`dbt.project_dir`, and select that root. External settings directories are no
longer supported. No alternative environment aliases are read.

### Relative paths

| Path | Relative to |
| --- | --- |
| `--project-dir`, `EXTRA_PROJECT_DIR`, `DBT_PROJECT_DIR`, Python `Project(directory)` | Current working directory |
| CLI `--manifest PATH`, `import PATH` | Current working directory |
| Configured `dbt.artifacts.*`, `export.output_dir`, dbt resource paths | Project root |
| CLI export `--output-dir` / `--path` | Project root |

Absolute paths remain absolute (resource paths must still stay within the project).
No existence-based guessing changes these rules. Setting `EXTRA_PROJECT_DIR` or
`DBT_PROJECT_DIR` does not change the working directory or rebase import paths.

For everyday commands, `cd` into the dbt project. From this repository checkout,
use `uv run extra`.

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

## Write boundaries

Unlike inspection/export expansion, `optimization.expand: true` can replace
authored macro calls and static templates with SQL. Relation/config calls remain
authored. Use `--preview` before applying; `optimize --expand false` explicitly
overrides configured expansion. See [optimizer safety](../guides/source-optimizer-safety.md).

Metadata proposals fill missing values only in existing dbt YAML model entries;
no properties files are created. See [metadata enrichment](../guides/metadata-enrichment.md).

Keep analysis, inspection, export, optimization and metadata tool settings here.
Resource paths belong in `dbt_project.yml`; business metadata belongs in dbt
properties. Credentials and execution profiles stay in dbt's own configuration.
