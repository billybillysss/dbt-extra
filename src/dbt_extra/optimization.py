"""Coordinate checked project changes around the project-independent SQL engine."""

from dbt_extra.errors import SpecError
from dbt_extra.files.changes import digest
from dbt_extra.project.model_sql import parse_model
from dbt_extra.project.schema_evidence import SourceSchemas
from dbt_extra.sql.templates.macros import macro_calls
from dbt_extra.sql.rewrites.engine import rewrite_sql
from dbt_extra.sql.rewrites.expressions import retained_boundaries
from dbt_extra.workflow_results import WorkflowChanges


def optimize(project, *, select=None, exclude=None, format="pretty", expand=False):
    """Rewrite authored SQL, optionally replacing supported local macros with SQL."""
    dialect = project.require_dialect()
    if format not in {"pretty", "compact"}:
        raise SpecError("optimization.format must be pretty or compact")
    changes, skipped = WorkflowChanges(project.root), {}
    evidence = SourceSchemas(project)
    for path, data in project.contents.items():
        # All evidence shares this immutable snapshot, including absent inputs.
        changes.watch(path, digest(data), check=True, external=not path.is_relative_to(project.root))
    for resource in project.select(select, exclude, kinds={"model"}):
        if not resource.path or resource.path.suffix != ".sql":
            skipped[resource.id] = "Read-only artifact/package or non-SQL model"
            continue
        changes.watch(resource.path, digest(project.contents[resource.path]), check=True)
        report = {}
        try:
            candidate = rewrite_sql(
                resource.code, dialect, pretty=format == "pretty", report=report, expand=expand,
                parse=lambda code: parse_model(project, code, expand=expand),
                parse_expanded=lambda code: parse_model(project, code, expand=True),
                schema_for=evidence.for_parsed, terminate=False,
            )
            before = parse_model(project, resource.code, expand=expand).tree
            after = parse_model(project, candidate).tree
        except SpecError as exc:
            skipped[resource.id] = str(exc)
            continue
        if candidate.encode("utf-8") == project.contents[resource.path]:
            status = "unchanged"
        elif expand and macro_calls(resource.code):
            status = "rewritten"
        elif before == after:
            status = "formatted"
        else:
            status = "rewritten" if report.get("rewritten") else "qualified"
        changes.set(resource.path, candidate)
        changes.optimization_report[resource.id] = {
            "status": status,
            "formatting_only": status == "formatted",
            "changed": candidate.encode("utf-8") != project.contents[resource.path],
            "retained": retained_boundaries(after),
            "outcomes": report.get("outcomes", []),
        }
        for outcome in changes.optimization_report[resource.id]["outcomes"]:
            outcome["resource_id"] = resource.id
    return changes, skipped
