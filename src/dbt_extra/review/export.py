"""Build dbt review documents, baselines, and checked output writes."""

from dbt_extra.analysis import catalog
from dbt_extra.errors import SpecError
from dbt_extra.files.changes import ChangeSet, content, digest
from dbt_extra.files.paths import safe_path
from dbt_extra.review import csv, json
from dbt_extra.review.contract import HEADERS, json_text
from dbt_extra.review.workbook import workbook_for


def tables_for(document):
    tables = {key: [] for key in HEADERS}
    for resource in document["resources"]:
        identity = {key: resource[key] for key in ("resource_id", "package", "model_path", "name")}
        props = {k: v for k, v in resource["properties"].items() if k not in {"name", "description", "columns"}}
        tables["resources"].append({**identity, "resource_type": resource["resource_type"], "source_file": resource["source_file"],
            "description": resource["description"] or "", "properties": json_text(props), "sql": resource["sql"].replace("\r\n", "\n").replace("\r", "\n"),
            "status": resource["status"], "reason": resource["reason"] or ""})
        for column in resource["columns"]:
            props = {k: v for k, v in column["properties"].items() if k not in {"name", "description", "data_type"}}
            tables["columns"].append({**identity, "column": column["name"], "expression": column.get("expression", ""),
                "description": column["description"] or "", "data_type": column["data_type"] or "", "properties": json_text(props),
                "upstream_columns": json_text(column["upstream_columns"]), "status": column["status"]})
    return tables


def baseline_for(project, tables):
    paths = {project.root / "dbt_project.yml"}
    if project.config_path.is_file() and project.config_path.is_relative_to(project.root):
        paths.add(project.config_path)
    for row in tables["resources"]:
        resource = project.resources[row["resource_id"]]
        paths.update(p for p in (resource.path, resource.property_path) if p)
    # Selected model-only reviews may depend on unselected macro files.
    paths.update(r.path for r in project.resources.values() if r.kind == "macro" and r.path)
    for path in paths | {project.config_path}:
        if content(path) != project.contents.get(path):
            raise SpecError(f"Conflict: {path} changed while preparing export")
    return {"format_version": 1, "project": project.name,
             "tool_config": digest(project.config_content), "tables": tables,
             "macro_files": sorted(r.source_file for r in project.resources.values() if r.kind == "macro" and r.path),
             "files": {p.relative_to(project.root).as_posix(): digest(content(p)) for p in sorted(paths)}}


def export_review(project, *, format="xlsx", output_dir=None, select=None, exclude=None, preview=False, expand=False):
    if format not in {"xlsx", "csv", "json"}:
        raise SpecError(f"Unknown export format: {format}")
    destination = (project.root / (output_dir or "extra/review")).absolute()
    safe_path(destination)
    destination = destination.resolve()
    for protected in [*project.model_roots, *project.macro_roots, *project.snapshot_roots, *project.seed_roots]:
        if destination == protected or destination.is_relative_to(protected):
            raise SpecError("Review output cannot be inside dbt input directories")
    document = catalog(project, project.select(select, exclude), expand=expand)
    tables = tables_for(document)
    baseline = baseline_for(project, tables)
    baseline["expanded_macros"] = expand
    if format == "json":
        outputs = json.outputs(document)
    elif format == "xlsx":
        outputs = {"review.xlsx": workbook_for(project, document, tables, baseline, expand=expand)}
    else:
        outputs = csv.outputs(tables, baseline)
    # Generated exports are deliberately not pruned and cannot touch authored files.
    paths = [destination / name for name in outputs]
    source_paths = {r.path for r in project.resources.values()} | {r.property_path for r in project.resources.values()}
    for path in paths:
        safe_path(path)
        if path in source_paths or path in {project.config_path, project.root / "dbt_project.yml", project.manifest_path}:
            raise SpecError(f"Export would overwrite an input: {path}")
    changes = ChangeSet(destination)
    for name, data in outputs.items():
        changes.set(destination / name, data)
    return changes.apply(preview=preview), document["coverage"]
