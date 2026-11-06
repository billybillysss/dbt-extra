# Architecture

The public CLI is dbt-only and offline. It never invokes dbt or a warehouse.

![dbt-extra offline architecture: project loading and shared SQL analysis feed inspection, optimization, and review workflows, with proposed source changes applied through checked writes.](architecture.png)

[Edit the architecture diagram](architecture.drawio).

## Components

| Component | Responsibility |
| --- | --- |
| Entry points | CLI and Python API orchestrate workflows over shared components |
| Project loading | Discover dbt resources, resolve identities and source locations, and select scope |
| SQL & analysis | Parse and render SQL/templates; resolve references, dependencies, query scopes, types, lineage and coverage reasons |
| Inspect & validate | Expand upstream logic, prune columns, explain logical plans and check project structure |
| Optimize & enrich | Propose SQL/YAML improvements using shared project and analysis primitives |
| Review exchange | Export XLSX/CSV and read-only JSON; validate supported imports against baselines and source bindings |
| Change handling | Collect proposed bytes, preview diffs and apply checked writes; project adapters preserve dbt YAML formatting |

`Project` and `ChangeSet` are available from `dbt_extra`. Source-edit workflows return proposed
changes rather than writing implicitly; callers can inspect `diffs()` before
`apply()`. See the [Python API reference](../reference/python-api.md) for imports,
signatures, reports and the exporting exception to deferred writes.

## Boundaries

The source layout separates workflow coordination from reusable mechanisms:

```text
dbt_extra/
  inspection.py, optimization.py, enrichment.py, validation.py
  workflow_results.py       # Explicit workflow changes and reports
  project/
    model_sql.py            # Project macro definitions and model parsing
    references.py           # Resolve ref/source resource identities
    relations.py            # Resolve physical relation names
    schema_evidence.py      # Complete authored schemas, not documentation guesses
    property_edits.py       # Prepare dbt YAML/config changes
  analysis/
    results.py, type_inference.py, lineage.py, dependencies.py
    column_demand.py        # Required-column propagation
    expansion.py            # Upstream definitions and operation-local caches
  sql/
    models.py, parser.py, renderer.py, qualification.py
    identifiers.py, aliases.py, scopes.py, edits.py, safety.py
    templates/
      syntax.py, interpreter.py, macros.py, expansion.py, config_format.py
    rewrites/
      engine.py, session.py, pipeline.py, regions.py
      structural.py, expressions.py, projections.py, query_boundaries.py
    functions/
      models.py, registry.py, <dialect>.py
  review/
    export.py, import_.py, contract.py, csv.py, json.py, shorthand.py
    xlsx/
      layout.py, styles.py, writer.py, reader.py
  files/
    changes.py, paths.py, yaml.py
```

- Root workflows coordinate project snapshots, analysis and checked proposals;
  the SQL rewrite engine does not load a `Project`.
- `sql` does not import `project`, `analysis`, review formats or workflows.
  Project-aware adapters supply parsing and schema providers explicitly.
- Template interpretation receives definitions and a package name, not a project.
  The syntax/interpreter/static-expansion layers do not import the SQL parser.
- `files` handles generic bytes, paths and YAML mechanics; it does not import
  project, SQL, analysis or review code. `PropertyEdits` prepares dbt-specific
  YAML changes on a `ChangeSet`.
- Review depends on the core, never the reverse. Display shorthand belongs to
  review; shared template syntax and checked SQL edits remain in `sql`.
- Function records are independent of catalogs and lookup. Catalogs import
  records directly, not the package facade. Recognition, inferred types and
  rewrite permissions remain separate contracts.

`query_boundaries.simplify_query_boundaries` is shared structural simplification,
not inspection-specific cleanup. Rewrite sessions retain copy-on-attempt rollback,
binding requirements and interface validation. Evaluation barriers are not merely
volatility: unknown or fallible anonymous calls can also block movement/sharing.

Only canonical module paths are provided; removed paths and names have no
compatibility wrappers or aliases. Use `Project.find_model`, `ParsedSQL`,
`FunctionSpec`, `FunctionShape`, and the standalone optimizer at
`dbt_extra.sql.rewrites.engine.optimize_source`.

Stable IDs and actual source locations remain separate from directory-only
`model_path`. Arbitrary templates are never executed; static macro previews use
an allowlisted AST interpreter with output/operation/depth limits, not dbt or
Jinja runtime execution. Manifest/catalog data is evidence,
never compiled-to-source reconstruction. Projects are operation-local snapshots.

## Checked writes

Writes assemble and validate complete proposed changes and check input snapshots.
Preview shows diffs without creating files. Apply stages sibling temporary files,
replaces targets, and attempts rollback after failures. No crash-safe transaction
or concurrency lock is claimed. Export writes review files only and never prunes.

## Development fixture

`examples/jaffle_shop` is the shared demo and native dbt integration fixture.
Run source-editing workflows against a temporary copy to preserve its teaching examples.
