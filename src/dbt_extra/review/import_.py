"""Validate review edits and propose changes to their original dbt files."""

import copy
from pathlib import Path

from sqlglot import exp

from dbt_extra.errors import SpecError
from dbt_extra.files.changes import ChangeSet
from dbt_extra.files.paths import within
from dbt_extra.review.contract import EDITABLE, HEADERS, key_for, structured
from dbt_extra.review.csv import read_csv
from dbt_extra.review.workbook import read_workbook
from dbt_extra.sql.jinja import validate_template
from dbt_extra.sql.parser import UnsupportedSQL, parse_authored
from dbt_extra.sql.macros import parse_model, macro_calls, single_expression, contains_opaque
from dbt_extra.sql.renderer import render
from dbt_extra.sql.scopes import rewrite_scopes


def read_review(path, *, workbook_edits=None):
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        return read_workbook(path, workbook_edits=workbook_edits)
    return read_csv(path)


def import_review(project, path):
    workbook_edits = []
    tables, baseline = read_review(path, workbook_edits=workbook_edits)
    if "format" in baseline or baseline.get("format_version") != 1 or baseline.get("project") != project.name:
        raise SpecError("Review baseline is incompatible with this dbt project; re-export before editing")
    changes = ChangeSet(project.root)
    changes.metadata_skipped = {}
    edited = {name: {} for name in HEADERS}
    for name, rows in tables.items():
        original = {key_for(name, r): r for r in baseline["tables"][name]}
        seen = set()
        for row in rows:
            key = key_for(name, row)
            if key in seen:
                raise SpecError(f"Duplicate {name} row: {key}")
            seen.add(key)
            if key not in original:
                raise SpecError(f"Unknown {name} identity: {key}; re-export to add discovered columns/resources")
            previous = original[key]
            for header in HEADERS[name]:
                if header not in EDITABLE[name] and row[header] != previous[header]:
                    raise SpecError(f"Read-only field changed: {name}.{header} ({key})")
            if row != previous:
                edited[name][key] = row
        if seen != set(original):
            raise SpecError(f"Rows were removed from {name}; explicit resource/column deletion is not supported")
    config_edits = [e for e in workbook_edits if "config_path" in e]
    template_sql_edits = {e["template_resource_id"] for e in workbook_edits if "template_resource_id" in e}
    scope_edits = {}
    for edit in workbook_edits:
        if "resource_id" in edit:
            scope_edits.setdefault(edit["resource_id"], []).append(edit)
    affected = set(edited["resources"]) | {k[0] for k in edited["columns"]} | set(scope_edits)
    affected.update(uid for edit in workbook_edits for uid in edit.get("macro_resource_ids", []))
    if affected or config_edits:
        changes.watch(project.config_path, baseline.get("tool_config"), check=True,
                      external=not project.config_path.is_relative_to(project.root))
        for path in (project.root / "dbt_project.yml", project.config_path):
            relative = path.relative_to(project.root).as_posix() if path.is_relative_to(project.root) else None
            if relative in baseline["files"]:
                changes.watch(path, baseline["files"][relative], check=True)
    for edit in config_edits:
        value = structured(edit["changes"]["config"], "Configuration")
        changes.project_config(project, edit["config_path"], value)
    for uid in sorted(affected):
        if uid not in project.resources:
            raise SpecError(f"Resource no longer exists: {uid}")
        resource = project.resources[uid]
        if not resource.path or resource.package != project.name:
            raise SpecError(f"Read-only resource: {uid}")
        old = next(r for r in baseline["tables"]["resources"] if r["resource_id"] == uid)
        if (resource.name, resource.model_path, resource.source_file, resource.kind) != (old["name"], old["model_path"], old["source_file"], old["resource_type"]):
            raise SpecError(f"Resource identity changed since export: {uid}")
        for p in {resource.path, resource.property_path} - {None}:
            relative = p.relative_to(project.root).as_posix()
            if relative not in baseline["files"]:
                raise SpecError(f"Property location changed since export: {uid}")
            changes.watch(p, baseline["files"][relative], check=True)
        proposed = copy.deepcopy(resource.properties)
        row = edited["resources"].get(uid, old)
        if resource.kind == "model" and resource.path.suffix == ".sql":
            for relative in baseline.get("macro_files", []):
                changes.watch(within(project.root, relative), baseline["files"][relative], check=True)
        if row["description"] != old["description"]:
            if row["description"]:
                proposed["description"] = row["description"]
            else:
                proposed.pop("description", None)
        if row["properties"] != old["properties"]:
            extra = structured(row["properties"], uid, {"name", "description", "columns", "tables"})
            proposed = {k: v for k, v in proposed.items() if k in {"name", "description", "columns"}}
            proposed.update(extra)
        expression_edits = {}
        for (rid, column), col in edited["columns"].items():
            if rid != uid:
                continue
            previous = next(c for c in baseline["tables"]["columns"] if c["resource_id"] == uid and c["column"] == column)
            if col["expression"] != previous["expression"]:
                if baseline.get("expanded_macros") and macro_calls(old["sql"]):
                    raise SpecError(f"Expanded macro expressions are read-only: {uid}")
                expression_edits[column] = col["expression"]
            if any(col[h] != previous[h] for h in {"description", "data_type", "properties"}):
                columns = proposed.setdefault("columns", [])
                target = next((c for c in columns if c["name"] == column), None)
                if target is None:
                    target = {"name": column}
                    columns.append(target)
                for header in ("description", "data_type"):
                    if col[header] != previous[header]:
                        if col[header]:
                            target[header] = col[header]
                        else:
                            target.pop(header, None)
                if col["properties"] != previous["properties"]:
                    extras = structured(col["properties"], f"{uid}.{column}", {"name", "description", "data_type"})
                    for key in list(target):
                        if key not in {"name", "description", "data_type"}:
                            del target[key]
                    target.update(extras)
        proposed.setdefault("name", resource.name)
        if proposed != resource.properties and (resource.properties or proposed != {"name": resource.name}):
            if resource.property_path:
                changes.properties(project, resource, proposed)
            else:
                changes.metadata_skipped[uid] = "No existing writable dbt YAML entry; add one in dbt and re-export"
        full_sql_changed = row["sql"] != old["sql"]
        if full_sql_changed and (expression_edits or uid in scope_edits) and uid not in template_sql_edits:
            raise SpecError(f"Edit SQL or expressions, not both: {uid}")
        if full_sql_changed:
            if resource.kind not in {"model", "snapshot", "macro"} or resource.path.suffix != ".sql":
                raise SpecError(f"SQL is read-only for {uid}")
            validate_template(row["sql"], uid)
            if resource.kind == "model":
                try:
                    parse_authored(row["sql"], project.require_dialect(), uid)
                except UnsupportedSQL:
                    pass  # Opaque templates receive structure checks, not compilation.
            if not (expression_edits or uid in scope_edits):
                changes.set(resource.path, row["sql"])
        if expression_edits or uid in scope_edits:
            if resource.kind != "model" or resource.path.suffix != ".sql":
                raise SpecError(f"Expression rewriting unavailable: {uid}")
            parse = lambda code: parse_model(project, code, uid, partial=True)
            parsed = parse(row["sql"] if full_sql_changed else resource.code)
            rewrite_scopes(parsed, scope_edits.get(uid, []), project.dialect, uid, parser=parse)
            if expression_edits and (not isinstance(parsed.tree, exp.Select) or any(p.is_star for p in parsed.tree.selects)):
                raise SpecError(f"Expression rewriting requires a simple explicit output SELECT: {uid}")
            for column, expression in expression_edits.items():
                outputs = [p for p in parsed.tree.selects if p.output_name == column]
                if len(outputs) != 1:
                    raise SpecError(f"Ambiguous output expression: {uid}.{column}")
                value = parse("SELECT " + expression)
                candidate = single_expression(value, column)
                original = outputs[0]
                if contains_opaque(original, parsed):
                    raise SpecError(f"Unresolved macro output is read-only: {uid}.{column}")
                alias = original.args["alias"].copy() if isinstance(original, exp.Alias) else exp.to_identifier(column, quoted=True)
                original.replace(exp.Alias(this=candidate.copy(), alias=alias))
                parsed.refs.update(value.refs)
                parsed.macros.update(value.macros)
                parsed.macro_aliases.update(value.macro_aliases)
            candidate = render(parsed.tree, parsed, project.dialect, prefix=True)
            parse(candidate)
            changes.set(resource.path, candidate)
    return changes
