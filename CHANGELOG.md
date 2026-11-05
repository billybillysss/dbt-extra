# Changelog

## Unreleased

## 0.1.0 — Initial release

First version of **dbt-extra**.

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
