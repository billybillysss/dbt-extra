# Compatibility and versioning

## Current boundaries

| Surface | Current contract |
| --- | --- |
| Package | `dbt-extra`, version `0.2.3`; distributed through PyPI, pre-1.0. Executable `extra`, Python namespace `dbt_extra`. Pin and test upgrades. |
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
version is not certification of every later release; CI tests the minimum and
freshly resolved SQLGlot against optimizer regressions, plus a freshly resolved
installed wheel.

## SQL dialects

- **Accepted names:** SQLGlot dialect names, not a closed adapter allowlist.
- **Shared regression matrix:** `duckdb`, `postgres`, `snowflake`, `bigquery`,
  `spark`, `tsql`, `fabric`, `databricks`, `redshift`, `trino`, and `athena` for offline
  parsing, rendering and rewrites.
- **Execution checks:** DuckDB differential tests, independent Jinja checks and
  an opt-in real dbt-duckdb before/after rebuild; opt-in local Spark 4.2.1 with ANSI
  mode on/off; and a dedicated PostgreSQL 16 service lane for portable optimizer
  cases. Engine execution is separate from cross-dialect parse/render coverage.
  These do not certify all rules/types, other warehouses or engine versions.
  See the [rule coverage limits](guides/source-optimizer-safety.md#regression-coverage).

Manifest autodetection translates only differing adapter names: `fabricspark`
to `spark`, and `sqlserver` to `tsql`. `fabric` keeps SQLGlot's dedicated Fabric
Warehouse dialect, not generic T-SQL; `databricks` likewise remains `databricks`.
Explicit CLI/configuration choices use SQLGlot names and override autodetection.
Unknown adapters require an explicit choice rather than a generic SQL fallback.

Dialect-specific arithmetic rewrites have separate, conservative permissions.
Related SQLGlot dialects do not automatically inherit them. A future dedicated
`fabricspark` dialect would require a reviewed mapping change and regression tests,
not an automatic switch based on the installed dependency version.

See [partial optimization](guides/partial-optimization.md) for rule-specific
boundaries, rule-checkpoint recovery and outcome reporting. Unknown or
volatile expressions do not veto independent safe work. Unproven fallible
outputs and joins are retained. Authored
top-level static templates remain intact unless expansion is explicitly enabled.

SQL-function type inference has its own
[implemented function catalogs](reference/sql-functions/README.md#implemented-dialect-catalogs),
with separate recognition/shape, type, rewrite-safety and enrichment tests. The
generated catalog table is the source for current counts; these are not counts
of SQLGlot-native functions or exhaustive inventories. Parsing/rendering coverage
alone does not certify enrichment or warehouse execution.

## Distribution status

Published distributions are available on [PyPI](https://pypi.org/project/dbt-extra/).
Install with `uv tool install dbt-extra` for the CLI or `uv add dbt-extra` for a
project dependency. Record the installed version when reporting results; for a
source checkout, also record the Git commit.

Package availability does not imply public source access. The GitHub repository
is currently private; source examples and linked GitHub documentation require
repository access. Package and source availability are independent.

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
