# Concepts and boundaries

## One source of truth

dbt SQL, property YAML, macros and snapshots are authoritative. Optional
`extra_project.yaml` contains tool settings only. Tables/JSON are derived reviews;
supported edits patch original files, not a second transformation language.

## Analysis is not execution

Shared internal context carries IDs, source paths, authored SQL/Jinja, optional
artifact evidence, columns, dependencies and availability reasons. Unknown schema
and opaque templates stay unknown. dbt-extra never executes arbitrary Jinja, runs dbt
or queries a warehouse. Supported local macros use a bounded, allowlisted static
interpreter, not the Jinja runtime. Business metrics can remain in a separate
semantic layer.

Inspection explains definitions, retaining joins, filters and multiplicity.
Expanding definitions does not prove equivalence to stored incremental/history
data. Logical optimization is refactoring, not warehouse performance tuning.
Value-lineage origins alone do not explain joins, filters or business grain.

## Directory-based review

`model_path` is a slash-separated project-relative parent directory, never a filename.
It includes the root folder: `models/staging`, `macros`, `seeds`. IDs and names stay separate. Paths are
read-only; selectors use actual project-relative source paths.

## Editing ownership

Only local authored resources are writable. Import checks export baselines;
optimization checks its loaded snapshot. Writes are staged with rollback attempts,
not transactions/locking. Review diffs and run dbt checks independently. See the
[review contract](reference/catalogs.md).
