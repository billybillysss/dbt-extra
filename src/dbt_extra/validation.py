"""Offline project/template/reference checks; not a dbt parse or build."""

from dbt_extra.analysis.dependencies import dependencies, validate_cycles
from dbt_extra.sql.jinja import validate_template
from dbt_extra.sql.parser import UnsupportedSQL, parse_authored


def validate(project):
    skipped, graph = {}, {}
    for resource in project.resources.values():
        if not resource.path or resource.path.suffix != ".sql":
            continue
        validate_template(resource.code, resource.id)
        if resource.kind != "model":
            continue
        if not project.dialect:
            skipped[resource.id] = "No SQL dialect available"
            continue
        try:
            parsed = parse_authored(resource.code, project.dialect, resource.id)
        except UnsupportedSQL as exc:
            skipped[resource.id] = str(exc)
            continue
        graph[resource.id] = dependencies(project, parsed)
    validate_cycles(graph)
    return skipped
