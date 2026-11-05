# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Entries are grouped by change type, with the newest version first. Unreleased
changes receive a version and an ISO 8601 release date when released.

## [Unreleased]

## [0.2.0] - 2026-11-04

### Added

- SQL-function enrichment reference with executable Spark and T-SQL examples,
  unresolved-function cases, inference boundaries and a shared path for adding
  coverage. These are offline metadata checks, not new warehouse integrations.
- Dialect-local semantics for 162 demonstrated SQLGlot Anonymous-function gaps:
  86 Spark and 76 T-SQL functions, with separate per-function recognition, shape,
  return-type, rewrite-safety and metadata-enrichment tests. The folder-based
  function reference lists all implementations and their type policies; unknown
  types and generator schemas remain conservative.
- Automatic formatting of leading Jinja `config()` calls during optimization:
  `pretty` expands arguments and nested dictionaries/lists, while `compact` uses
  a single line except for authored multiline strings. Formatting preserves quotes, values,
  key order, and Jinja semantics without evaluating templates or adding dependencies;
  other Jinja calls and review-import formatting remain unchanged.

### Changed

- Centralize SQL dialect resolution and conservative arithmetic rewrite permissions.
  Preserve `fabric` as its dedicated SQLGlot dialect, map manifest `fabricspark`
  to `spark` and `sqlserver` to `tsql`, and report invalid choices consistently.
  Share the offline dialect regression matrix and include Fabric Warehouse,
  Databricks, Redshift, Trino and Athena;
  warehouse execution coverage remains DuckDB-only.
- **Breaking:** Unify project selection around the directory containing
  `dbt_project.yml`: `--project-dir` > `EXTRA_PROJECT_DIR` > nearest ancestor dbt
  project. Load optional settings only at that root; reject legacy
  `dbt.project_dir` with migration guidance. `init` uses the shared resolver and
  no longer accepts a positional directory; use `extra --project-dir PATH init`.
  CLI input paths remain current-directory-relative; configured paths and export
  destinations remain project-root-relative.
- **Breaking:** Replace `optimize --preserve-macro` with `--expand true|false`
  (default: false). Opting in writes supported static local macros as SQL, then
  optimizes it; unsupported models are skipped unchanged. Relation/config calls
  remain authored. Rename `optimization.preserve_macros` to `optimization.expand`
  with inverted polarity.

### Fixed

- Preserve authored output names and quoted relation identities during Snowflake
  type inference and lineage, without creating uppercase duplicate YAML columns.
- Handle Redshift's empty parsed `EXCLUDE` clause in guarded rewrites, and retain
  `QUALIFY` window-alias definitions during SQLGlot 30.29 inspection optimization.

### Removed

- **Breaking:** Remove `--dry-run`; use `--preview` as the sole no-write flag on
  writing commands.

## [0.1.0] - 2026-11-04

Initial release of **dbt-extra**.

### Added

- Distribution `dbt-extra`, Python package `dbt_extra`, and CLI `extra`.
- Native dbt SQL, property YAML, macros and snapshots remain authoritative.
- Offline validation, full-model and selected-column inspection, logical plans,
  bounded local macro previews, and explicit analysis coverage reasons.
- Folder-grouped XLSX and CSV reviews, read-only JSON catalogs, and
  baseline-checked edits back to authored files with YAML comment preservation.
- Conservative source SQL optimization and missing-metadata enrichment;
  `--preview` / `--dry-run` writes nothing.
- Optional `extra_project.yaml` and `EXTRA_PROJECT_DIR`; review exports default
  to `extra/review/` with format version 1 and no branded format identifiers.
- Metadata enrichment and review import update existing dbt YAML entries only;
  missing entries are reported and skipped, never created automatically.
- Documentation, executable Jaffle Shop examples and native dbt integration
  fixture, tests, package smoke checks and cross-platform CI.
- MIT licensing and third-party Apache 2.0 seed attribution.
- Adopted the maintainer-supplied Modular joint / Lagoon SVG icon, preserving
  its paths and palette across light/dark variants, plus a monochrome asset.
- PyPI trusted publishing after CI on `v*` tags or manual dispatch, with
  release-tag/package-version verification for tag runs.

[Unreleased]: https://github.com/billybillysss/dbt-extra/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/billybillysss/dbt-extra/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/billybillysss/dbt-extra/releases/tag/v0.1.0
