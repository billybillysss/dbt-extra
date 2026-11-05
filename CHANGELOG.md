# Changelog

## Unreleased

## 0.1.0 — Initial private preview

First version of **dbt-extra**, migrated from slbt with fresh repository history.

- Distribution `dbt-extra`, Python package `dbt_extra`, and CLI `extra`.
- Native dbt SQL, property YAML, macros and snapshots remain authoritative.
- Offline validation, full-model and selected-column inspection, logical plans,
  bounded local macro previews, and explicit analysis coverage reasons.
- Folder-grouped XLSX and CSV reviews, read-only JSON catalogs, and
  baseline-checked edits back to authored files with YAML comment preservation.
- Conservative source SQL optimization and missing-metadata enrichment;
  `--preview` / `--dry-run` writes nothing.
- Optional `extra_project.yaml`, `EXTRA_PROJECT_DIR`, `extra_review`, and
  `_extra_properties.yml`; branded review envelopes use `dbt-extra.dbt-review`
  and `dbt-extra.dbt-review-baseline` with format version 2.
- Migrated documentation, executable Jaffle Shop examples, handwritten dbt
  integration fixture, tests, package smoke checks and cross-platform CI.
- Retained MIT licensing and third-party Apache 2.0 seed attribution.
- Adopted the maintainer-supplied Modular joint / Lagoon SVG icon, preserving
  its paths and palette across light/dark variants, plus a monochrome asset.
- Removed the obsolete version-1 authoring example and old wordmark/diagram
  artwork from this new repository.
- Kept release-candidate verification only; no automatic PyPI publishing.

See [migration instructions](docs/guides/migrating-from-slbt.md) for the breaking
name changes. No old-name compatibility aliases or in-place review conversion
are provided. The original repository and local checkout are unchanged.
