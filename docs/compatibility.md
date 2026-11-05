# Compatibility and versioning

## Current boundaries

| Surface | Current contract |
| --- | --- |
| Package | `dbt-extra`, version `0.1.0`; private preview, pre-1.0. Executable `extra`, Python namespace `dbt_extra`. Pin and test upgrades. |
| Python | Metadata requires 3.11+. CI targets 3.11 and 3.13 on Linux, plus 3.13 on Windows. Other Python/platform combinations are not thereby certified. |
| SQLGlot | Runtime dependency is constrained to `>=30.8,<30.25`, tested at 30.8.0 and 30.24.0. Dialect availability does not establish warehouse execution support. |
| Tool settings | Optional `extra_project.yaml`, `version: 2`; no transformation authoring schema. |
| Review JSON | `format_version: 1`, `source_of_truth: dbt`. Read-only analysis; check coverage and the envelope. |
| dbt | Native authored SQL/properties/macros/snapshots. No compile/runtime emulation. Execution compatibility depends on your dbt and adapter versions. The native demo uses DuckDB. |
| Python internals | Not a separately guaranteed stable public API. Prefer the CLI or explicitly version-tested integrations. |

CI declares test targets; a new matrix entry is not proof it has passed until
that workflow runs successfully. The development environment uses DuckDB for
local execution checks; it does not run a remote warehouse integration.
No macOS CI or warehouse performance benchmark is currently provided.

The supported range stops before 30.25: 30.25.0 failed existing window-alias
`QUALIFY` regressions, and fresh-install checks with 30.29.0 exposed further API
and SQL-rendering differences. The exclusion is not a general certification of
every other SQLGlot version; CI also tests a freshly resolved installed wheel.

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

Use `optimization.preserve_macros: true`; native rewrites never expand macros.
`--preview` is the unified no-write option; `--dry-run` remains an alias.

## Maintainer policy for future changes

Record user-visible changes under Unreleased. Document CLI/config/schema changes,
add regression tests, and provide migration instructions for incompatible changes.
If the JSON contract becomes incompatible, update its format version rather than
silently reinterpreting existing fields. Additive fields should not require
consumers to reject an otherwise supported envelope. dbt-extra does not currently
provide a general JSON Schema validator or migration service.
