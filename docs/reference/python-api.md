# Python API

Use these interfaces to integrate analysis and proposals into Python tools.
Pin dbt-extra and test upgrades; these interfaces do not have a separate stability guarantee.
The root package exports `Project`, `ChangeSet`, `SpecError` and `__version__`.

## Read a project and propose changes

Run this example from `examples/jaffle_shop`:

```python
from dbt_extra import Project
from dbt_extra.analysis import catalog
from dbt_extra.optimization import optimize

project = Project()  # Or Project("/path/to/project", dialect="duckdb").
document = catalog(project, project.select(["customer_revenue"]))
changes, skipped = optimize(project, select=["customer_revenue"])
print(changes.diffs())
# changes.apply()  # Explicitly accept the proposed source edits.
```

Construction, analysis and proposal generation do not write files. `Project`
loads an operation-local snapshot; create a fresh one after changing project
files. Source edits are checked against that snapshot at apply time.

## Project and selection

| Interface | Behavior |
| --- | --- |
| `Project(directory=None, *, dialect=None, manifest=None)` | Discover/load a dbt root; explicit dialect and manifest override settings |
| `project.select(selections=None, exclude=None, *, kinds=None)` | Return sorted resources using the [shared selectors](cli.md#select-resources); `kinds` optionally restricts resource kinds |
| `project.find_model(name)` | Resolve a model name or exact ID; reject unknown, nonmodel or ambiguous matches |
| `project.options(section, overrides=None, *, view=None)` | Merge workflow settings, optional export view and non-`None` overrides |

Project discovery and relative input paths follow the [configuration rules](configuration.md).
Useful snapshot attributes include `root`, `name`, `dialect`, `resources` (keyed by
ID), `diagnostics` and `settings`. Resources expose `id`, `name`, `kind`, `package`,
`source_file`, `model_path`, `code`, `properties` and source/property paths.
Artifact-only resources have no local source path. `model_path` is a parent
directory, not a filename or resource identity.

Workflow functions use their explicit arguments and Python defaults. They do
**not** automatically merge workflow settings like the CLI does. To honor those
settings, call `project.options(...)` and pass the supported resolved options.
Project loading still resolves `analysis.dialect` and configured artifacts.

## Workflow functions

| Import and signature | Returns / side effects |
| --- | --- |
| `dbt_extra.analysis.analyze(project, resource, *, expand=False)` | Analysis dictionary for one resource; no writes |
| `dbt_extra.analysis.catalog(project, resources, *, expand=False)` | JSON-compatible [analysis envelope](catalogs.md#read-only-json); no writes |
| `dbt_extra.validation.validate(project)` | Mapping of resource IDs to unavailable-analysis reasons; invalid supported structure/SQL/cycles raises an error |
| `dbt_extra.inspection.inspect(project, name, columns=None, *, boundaries=(), expanded=True, optimized=True, compiled=True)` | `(tree, parsed, issues)`; no writes |
| `dbt_extra.inspection.plan(tree, parsed, dialect)` | Logical-plan text |
| `dbt_extra.optimization.optimize(project, *, select=None, exclude=None, format="pretty", expand=False)` | `(changes, skipped)`; skipped maps resource IDs to reasons |
| `dbt_extra.enrichment.enrich(project, *, select=None, exclude=None, changes=None)` | `(changes, report)`; optionally adds metadata proposals to an existing ChangeSet |
| `dbt_extra.review.export_review(project, *, format="xlsx", output_dir=None, select=None, exclude=None, preview=False, expand=False)` | `(paths, coverage)`; **writes review files** unless preview is true |
| `dbt_extra.review.import_review(project, path)` | Proposed ChangeSet; does not apply it |

Render an inspection tree with
`dbt_extra.sql.renderer.render(tree, parsed, project.dialect)`. Inspection issues
include `resource_id` and `reason`; transformation issues also carry the
[outcome fields](../guides/partial-optimization.md#checkpoints-and-reporting).

Optimization and review import return `WorkflowChanges`, a `ChangeSet` subclass
defined in `dbt_extra.workflow_results` with explicit report fields.
Optimization populates `changes.optimization_report`, keyed by resource ID. Each
entry contains `status` (`rewritten`, `qualified`, `formatted`, `unchanged`),
`formatting_only`, `changed`, `retained` reasons and `outcomes`. Enrichment report
items contain a resource ID and either an inferred column/property/value or an
unresolved reason. Imports expose skipped metadata through
`changes.metadata_skipped`. Check these reports before applying proposals.

## Standalone SQL

`dbt_extra.sql.rewrites.engine.optimize_source(code, dialect, *, schema=None, pretty=True, outcomes=None)`
returns SQL without a project or filesystem writes:

```python
from dbt_extra.sql.rewrites.engine import optimize_source

outcomes = []
sql = optimize_source("SELECT 1 + 2 AS k", "duckdb", outcomes=outcomes)
assert "3 AS k" in sql
```

The optional schema is a complete, ordered relation mapping or native SQLGlot
schema. Supplying documentation columns as a partial schema is unsafe. See
[schema evidence](../guides/source-optimizer-safety.md#schema-evidence) and
[rewrite boundaries](../guides/source-optimizer-safety.md#rewrite-boundaries).

## ChangeSet and errors

`ChangeSet(root)` collects writes within a root. Workflow-generated instances
already include the required input watches and validation.

| Method | Behavior |
| --- | --- |
| `changes.changed()` | Mapping of changed paths to proposed bytes |
| `changes.diffs()` | Unified text diffs; no writes |
| `changes.apply(preview=True)` | Check watched inputs and return changed paths; no writes |
| `changes.apply()` | Check watched inputs, stage replacements and return written paths |

Do not reuse a snapshot/ChangeSet for another editing round after applying it.
Create a new project and proposal. Manually adding bytes with `ChangeSet.set()`
does not perform workflow-level SQL or metadata validation.

`dbt_extra.project.property_edits.PropertyEdits(changes)` prepares dbt YAML
property and configuration edits on an existing change set. Generic `ChangeSet`
handles checked byte writes only; it has no project-specific editing methods.

`SpecError` subclasses `ValueError` and reports project/contract violations,
unsupported operations and source conflicts. Filesystem and SQLGlot errors may
also propagate; do not catch every exception as an unsupported feature. Writes
attempt rollback on failure but provide neither crash-safe multi-file
transactions nor concurrency locks. See the [write boundaries](../guides/production-workflow.md#file-mutation-and-deployment).
