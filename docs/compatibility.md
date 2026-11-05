# Compatibility and versioning

## Current boundaries

| Surface | Current contract |
| --- | --- |
| Package | `dbt-extra`, version `0.2.0`; private preview, pre-1.0. Executable `extra`, Python namespace `dbt_extra`. Pin and test upgrades. |
| Python | Metadata requires 3.11+. CI targets 3.11 and 3.13 on Linux, plus 3.13 on Windows. Other Python/platform combinations are not thereby certified. |
| SQLGlot | Runtime dependency is `>=30.29.0`; the local function-gap catalog is checked against 30.29.0. Dialect availability does not establish warehouse execution support. |
| Tool settings | Optional `extra_project.yaml`, `version: 2`; no transformation authoring schema. |
| Review JSON | `format_version: 1`, `source_of_truth: dbt`. Read-only analysis; check coverage and the envelope. |
| dbt | Native authored SQL/properties/macros/snapshots. No compile/runtime emulation. Execution compatibility depends on your dbt and adapter versions. The native demo uses DuckDB. |
| Python internals | Not a separately guaranteed stable public API. Prefer the CLI or explicitly version-tested integrations. |

CI declares test targets; a new matrix entry is not proof it has passed until
that workflow runs successfully. The development environment uses DuckDB for
local execution checks; it does not run a remote warehouse integration.
No macOS CI or warehouse performance benchmark is currently provided.

SQLGlot upgrades require regression review, including window-alias `QUALIFY`,
rendering and the local function-gap catalog. New native recognition must retire
or revise a local entry rather than inflate the gap count. A minimum dependency
version is not certification of every later release; CI also tests a freshly
resolved installed wheel.

## SQL dialects

- **Accepted names:** SQLGlot dialect names, not a closed adapter allowlist.
- **Shared regression matrix:** `duckdb`, `postgres`, `snowflake`, `bigquery`,
  `spark`, `tsql`, `fabric`, `databricks`, `redshift`, `trino`, and `athena` for offline
  parsing, rendering and rewrites.
- **Execution checks:** DuckDB only; these tests do not certify other warehouses.

Manifest autodetection translates only differing adapter names: `fabricspark`
to `spark`, and `sqlserver` to `tsql`. `fabric` keeps SQLGlot's dedicated Fabric
Warehouse dialect, not generic T-SQL; `databricks` likewise remains `databricks`.
Explicit CLI/configuration choices use SQLGlot names and override autodetection.
Unknown adapters require an explicit choice rather than a generic SQL fallback.

Dialect-specific arithmetic rewrites have separate, conservative permissions.
Related SQLGlot dialects do not automatically inherit them. A future dedicated
`fabricspark` dialect would require a reviewed mapping change and regression tests,
not an automatic switch based on the installed dependency version.

SQL-function type inference has its own
[implemented function catalogs](reference/sql-functions/README.md): 86 Spark and
76 T-SQL SQLGlot gaps, with separate recognition/shape, type, rewrite-safety and
enrichment tests. These are not counts of SQLGlot-native functions. Other dialects
have no local gap catalog; dialect parsing/rendering coverage alone does not
certify enrichment or warehouse execution.

## Initial version

`dbt-extra` starts at `0.1.0` as a private preview.
Install from an authorized source checkout and record its Git commit when
reporting results. The repository stays private until
verification and separate maintainer approval to make it public.

Public visibility, package publication and branding are separate release gates;
see the [release checklist](development/releasing.md).

## Upgrade policy

Before upgrading, keep a Git baseline and export reviews into an isolated
directory. Compare validation, SQL, properties, review JSON, mutation diffs and
dbt results. Check [CHANGELOG](../CHANGELOG.md) for documented changes.

Use the responsibility-based packages described in [architecture](development/architecture.md)
for version-tested Python integrations. Review files must follow the
[review contract](reference/catalogs.md), including their export baseline.

Use `optimization.expand: false` (the default) to preserve macros. Set it true,
or use `optimize --expand true`, to write supported static local macros as SQL.
Replace the removed `optimization.preserve_macros` setting with `expand`, inverting
the boolean (`preserve_macros: true` becomes `expand: false`). The old
`--preserve-macro` flag is removed. Expansion is now supported, not merely a renamed
error path; review changes with `--preview` before applying.
`--preview` is the only no-write option; replace removed `--dry-run` usages with it.

## Maintainer policy for future changes

Record user-visible changes under Unreleased. Document CLI/config/schema changes,
add regression tests, and provide migration instructions for incompatible changes.
If the JSON contract becomes incompatible, update its format version rather than
silently reinterpreting existing fields. Additive fields should not require
consumers to reject an otherwise supported envelope. dbt-extra does not currently
provide a general JSON Schema validator or migration service.
