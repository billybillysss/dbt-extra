# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Entries are grouped by change type, with the newest version first. Unreleased
changes receive a version and an ISO 8601 release date when released.

## [Unreleased]

### Changed

- Add a reproducible five-step demo, with static SQL
  optimization boundaries and no warehouse performance claims.
- Document PyPI installation with `uv add dbt-extra` and the standalone uv tool
  option in the README.
- Consolidate column-tracing examples in `examples/jaffle_shop`, including the
  retained-join walkthrough, and remove the redundant standalone example.

## [0.2.1] - 2026-11-05

### Added

- Support `DBT_PROJECT_DIR` for CLI and Python project selection after
  `EXTRA_PROJECT_DIR` and before upward discovery. Explicit `--project-dir` and
  Python directory arguments still take precedence; invalid selections fail
  without falling back.
- Rule checkpoints and structured applied/blocked/rolled-back outcomes for SQL
  inspection and authored optimization. Recoverable rule failures discard only
  their candidate; independent validated work survives.
- Dependency-aware projection pruning for windows, QUALIFY, shared CTEs,
  aggregates, positional references and set operations, with evaluation-safety
  roots and retained global-aggregate cardinality.
- Bounded top-level literal Jinja assignments, loops and conditions. Inspection
  can render static SQL; authored templates remain byte-preserved by default and
  require explicit `optimize --expand true` for reduction.
- Generated synthetic dbt/temporal fixtures, repeated-dependency benchmark,
  minimum/fresh SQLGlot compatibility CI and local Spark ANSI execution tests.
- Strict execution oracles with deliberate broken-candidate checks, seeded
  multi-rule/asymmetric-input cases, independent real-Jinja comparisons, real
  before/after dbt-duckdb rebuilds, expanded Spark execution and a PostgreSQL 16 CI lane.
- Spark execution targets PySpark 4.2.1 with Java 21, verifying the actual running
  version so an inherited SPARK_HOME cannot silently test an older installation.
- Reproducible, source-linked first-pass SQL-function audit for the nine remaining
  dialects, separating native support, recognition gaps and type-inference gaps.
- Explicit SQL-function gap catalogs for Fabric Warehouse (3), Databricks (3),
  DuckDB (4), and PostgreSQL (6), with per-entry recognition, conservative typing,
  generator/safety and YAML-enrichment tests. Native functions, CLI-only DuckDB
  `getenv`, and unproven Fabric overloads remain outside the catalogs. This adds
  offline coverage, not warehouse execution certification.
- Complete the remaining SQL-function batches with explicit Snowflake (4),
  BigQuery (2), Redshift (4), Trino (4), and Athena engine-3 (4) gap entries,
  official-source audit evidence and per-function enrichment/safety regressions.
  Trino `bar` supports exactly two or four arguments; BigQuery contextual and
  nested input-dependent results remain unresolved. No native ASTs are replaced
  and no new function-evaluation or rewrite permission is granted.
- Python API reference, metadata-enrichment and partial-optimization guides, and
  multi-layer column-tracing examples in Jaffle Shop and `examples/column_trace`.

### Changed

- Unknown, volatile and fallible functions block affected evaluation movement,
  not unrelated constant folding. Binding failures retain SQL and disable
  binding-dependent rules instead of necessarily skipping the whole model.
- Inspection uses complete query-derived schema evidence, never assumes YAML
  documentation is exhaustive, and caches parsing, demands and expanded bodies
  within an operation. Repeated expansion diagnostics retain occurrence counts.
- Generated SQL aliases use readable input names with collision handling instead
  of internal counters, preserving authored aliases and correlated bindings.
  Long expanded names retain their original identity in comments.
- Conservatively remove single-use CTEs and column-only projection wrappers when
  evaluation, output bindings and row-affecting boundaries remain intact.
- **Breaking:** Rename `Project.find()` to `Project.find_model()`, `Parsed` to
  `ParsedSQL`, and function records `Function` / `Shape` to `FunctionSpec` /
  `FunctionShape`. Move standalone `optimize_source()` from
  `dbt_extra.optimization` to `dbt_extra.sql.rewrites.engine`.
- **Breaking:** Reorganize SQL templates and rewrites under `sql.templates` and
  `sql.rewrites`, project-aware SQL adapters under `project`, analysis records
  and type inference under `analysis.results` and `analysis.type_inference`,
  and workbook handling under `review.xlsx`. Review shorthand moves to
  `review.shorthand`; removed module paths and names have no compatibility aliases.
- **Breaking:** Move project-specific `ChangeSet.properties()` and
  `ChangeSet.project_config()` edits to `dbt_extra.project.property_edits.PropertyEdits(changes)`.
  Generic `ChangeSet` handles checked byte writes only; optimization and review
  import return `WorkflowChanges` with explicit report fields.

### Fixed

- EXISTS-to-IN rewriting now requires matching declared integral base-column
  types on explicitly tested engines; mixed/unknown types retain EXISTS instead
  of risking changed comparison coercion or binding errors.
- Optimized project models no longer gain statement terminators that break dbt
  materialization wrappers. Standalone SQL output still has a terminator.
- Static string methods follow real Jinja: `.strip()` is supported instead of
  the nonexistent `.trim()` method; the `trim` filter remains supported.
- Inspection no longer simplifies overflowing `(2147483647 + 1) * 0` to zero.
- Qualification avoids copying potentially fallible/volatile alias expressions.
  Local rewrites retain unnamed computed output labels and exact decimal types.
- Unused projected RHS columns alone no longer authorize erasing fallible join
  evaluation. SQL-derived uniqueness and matching proofs remain necessary.
- Predicate rewrites retain input-dependent comparisons when simplification
  would otherwise erase unproven implicit-conversion behavior.
- Match local function catalogs when validated dialect strings include settings,
  without dropping those settings from parsing or type inference. Validate source
  registrations before duplicate names can be overwritten, and make generator
  shape dispatch dialect-specific with an unknown-shape fallback for new entries.

### Removed

- **Breaking:** Remove legacy flat XLSX import support. Re-export affected
  workbooks using the current hierarchical layout before editing or importing.

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

[Unreleased]: https://github.com/billybillysss/dbt-extra/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/billybillysss/dbt-extra/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/billybillysss/dbt-extra/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/billybillysss/dbt-extra/releases/tag/v0.1.0
