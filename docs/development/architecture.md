# Architecture

The public CLI is dbt-only and offline. It never invokes dbt or a warehouse.

| Module under `src/dbt_extra/` | Responsibility |
| --- | --- |
| `cli.py` | Thin command orchestration; explicit options override settings |
| `config.py`, `errors.py` | Optional tool settings and shared errors |
| `project/` | dbt discovery, resource identity, properties, artifacts and selectors |
| `sql/` | Parsing, reversible shorthand/masking, bounded static macro interpretation, reference resolution, rendering and query scopes |
| `analysis/` | Shared analysis context, dependencies, types/value lineage and coverage reasons |
| `inspection.py` | Upstream expansion, column pruning and logical plans |
| `validation.py`, `optimization.py`, `enrichment.py` | Offline workflows over shared project and SQL primitives |
| `review/contract.py` | Format-independent review fields and editable boundaries |
| `review/export.py`, `review/import_.py` | Export baselines and checked import planning |
| `review/workbook.py` | Path-grouped hierarchical XLSX and cell/source bindings |
| `review/csv.py`, `review/json.py` | CSV serialization and read-only JSON output |
| `files/` | Safe paths, round-trip YAML patches, conflicts, staged writes and rollback |

`Project` and `ChangeSet` are available from `dbt-extra`. Source-edit workflows return proposed
changes rather than writing implicitly; callers can inspect `diffs()` before
`apply()`. SQL and analysis code do not depend on review formats. Scoped SQL
rewrites live in `sql/scopes.py`, not the spreadsheet serializer.

Stable IDs and actual source locations remain separate from directory-only
`model_path`. Arbitrary templates are never executed; static macro previews use
an allowlisted AST interpreter with output/operation/depth limits, not dbt or
Jinja runtime execution. Manifest/catalog data is evidence,
never compiled-to-source reconstruction. Projects are operation-local snapshots.

Writes assemble and validate complete proposed changes and check input snapshots.
Preview shows diffs without creating files. Apply stages sibling temporary files,
replaces targets, and attempts rollback after failures. No crash-safe transaction
or concurrency lock is claimed. Export writes review files only and never prunes.

`examples/jaffle_shop` is the shared demo and native dbt integration fixture.
Run source-editing workflows against a temporary copy to preserve its teaching examples.
