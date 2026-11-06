"""Project flat review tables into hierarchical sheets and authored bindings."""

import json
import re

from sqlglot import exp

from dbt_extra.errors import SpecError
from dbt_extra.project.model_sql import model_macro_calls, parse_model
from dbt_extra.project.properties import scope_config
from dbt_extra.review.contract import json_text
from dbt_extra.review.shorthand import display
from dbt_extra.sql.edits import clauses_text, editable_select
from dbt_extra.sql.renderer import render
from dbt_extra.sql.scopes import query_scopes
from dbt_extra.sql.templates.macros import contains_opaque, macro_calls
from dbt_extra.sql.templates.syntax import macro_blocks


MODEL_HEADERS = ["Type", "Path", "Name", "Distinct", "Key",
                 "Expression", "Data Type", "Description", "Config", "Constraints", "Tests", "Meta"]
SOURCE_HEADERS = ["Type", "Path", "Name", "Database", "Schema", "Identifier", "Loader", "Data Type",
                  "Source Data Type", "Description", "Config", "Tests", "Meta", "Properties"]
MACRO_HEADERS = ["Path", "Name", "Expression", "Description", "Properties", "Properties File"]
CONTEXT_HEADERS = ["Resource ID", "Package", "Source File", "Status", "Reason"]
ROW_ID = "_extra_row_id"


def build_layout(project, tables, *, expand=False):
    """Build path-grouped sheets without creating or styling an Excel workbook."""
    resources = {r["resource_id"]: r for r in tables["resources"]}
    columns = {}
    for row in tables["columns"]:
        columns.setdefault(row["resource_id"], []).append(row)
    sheets, groups = [], {}
    used_names = {"readme", "configuration", "_baseline"}

    def sheet_name(label):
        base = re.sub(r"[\\/*?:\[\]]", " · ", label).strip(" '") or "Models"
        name, suffix = base[:31], 1
        while name.casefold() in used_names:
            suffix += 1
            tail = f" ({suffix})"
            name = base[:31 - len(tail)] + tail
        used_names.add(name.casefold())
        return name

    def group_for(resource):
        category = "Sources" if resource.kind in {"source", "source_group"} else "Macros" if resource.kind in {"macro", "macro_definition"} else "Snapshots" if resource.kind == "snapshot" else "Seeds" if resource.kind == "seed" else "Models"
        folder = resource.model_path
        if resource.path:
            roots = project.macro_roots if category == "Macros" else project.seed_roots if category == "Seeds" else project.snapshot_roots if category == "Snapshots" else project.model_roots
            for root in roots:
                if resource.path.is_relative_to(root):
                    folder = resource.path.parent.relative_to(root if len(roots) == 1 else project.root).as_posix()
                    break
        key = category, resource.package, folder
        if key not in groups:
            label = folder if category == "Models" and folder != "." else category
            if category != "Models" and folder != ".":
                label += " · " + folder
            if resource.package != project.name:
                label = resource.package + " · " + label
            headers = SOURCE_HEADERS if category == "Sources" else MACRO_HEADERS if category == "Macros" else MODEL_HEADERS + ["Properties"]
            groups[key] = {"name": sheet_name(label), "headers": headers + CONTEXT_HEADERS + (["Authored SQL"] if category not in {"Sources", "Macros"} else []) + [ROW_ID], "rows": [], "category": category, "folder": folder}
            sheets.append(groups[key])
        return groups[key]

    def record(sheet, values, *, target=None, fields=None, props=None, residual=(), kind="COLUMN", level=0, editable=True, scope=None, metadata_editable=True, macro_binding=None, template_binding=None):
        original_expression = values.get("Expression", "")
        if sheet["category"] not in {"Macros", "Config"} and original_expression:
            values["Expression"] = display(original_expression)
        item = {"id": str(sum(len(s["rows"]) for s in sheets) + 1), "values": values, "target": target,
                "fields": fields or {}, "props": props or {}, "residual": list(residual), "kind": kind, "level": level,
                "editable": editable, "scope": scope, "metadata_editable": metadata_editable, "macro_binding": macro_binding,
                "template_binding": template_binding, "original_expression": original_expression}
        sheet["rows"].append(item)
        return item

    def metadata(values, props, *, source=False, column=False):
        bindings = {}
        fields = {"Config": "config", "Constraints": "constraints", "Meta": "meta"}
        fields["Tests"] = "data_tests" if "data_tests" in props or "tests" not in props else "tests"
        if source and not column:
            fields.update({"Database": "database", "Schema": "schema", "Identifier": "identifier", "Loader": "loader"})
        for header, key in fields.items():
            if header not in values:
                continue
            values[header] = (str(props[key]) if header in {"Database", "Schema", "Identifier", "Loader"} else json_text(props[key])) if key in props else ""
            bindings[header] = key
        excluded = set(bindings.values())
        values["Properties"] = json_text({k: v for k, v in props.items() if k not in excluded})
        return bindings, excluded

    # Documentation joins by actual macro name: one file may hold many macros.
    definitions = {(project.resources[uid].package, row["name"]): uid
                   for uid, row in resources.items() if project.resources[uid].kind == "macro_definition"}
    macros, matched, names = {}, set(), set()
    for uid, row in resources.items():
        resource = project.resources[uid]
        if resource.kind != "macro":
            continue
        for block in macro_blocks(row["sql"], resource.source_file):
            key = resource.package, block["name"]
            if key in names:
                raise SpecError(f"Ambiguous authored macro: {resource.package}.{block['name']}")
            names.add(key)
            definition = definitions.get(key)
            if definition:
                matched.add(definition)
            macros.setdefault(uid, []).append((block, definition))

    for uid, row in resources.items():
        if uid in matched:
            continue
        resource = project.resources[uid]
        sheet = group_for(resource)
        writable = resource.path is not None and resource.package == project.name and not resource.properties.get("versions")
        macro = sheet["category"] == "Macros"
        source = sheet["category"] == "Sources"
        if uid in macros:
            for block, definition in macros[uid]:
                target_uid = definition or uid
                doc = resources[target_uid]
                authored = json.loads(doc["properties"]) if definition else {}
                values = {"Path": resource.model_path, "Name": block["name"],
                          "Expression": row["sql"][block["start"]:block["end"]],
                          "Description": doc["description"] if definition else "",
                          "Resource ID": target_uid, "Package": resource.package,
                          "Source File": resource.source_file,
                          "Properties File": project.resources[definition].source_file if definition else "",
                          "Status": row["status"], "Reason": row["reason"]}
                props, excluded = metadata(values, authored)
                record(sheet, values, target=["resources", target_uid],
                       fields={"Expression": "sql", **({"Description": "description"} if definition else {})},
                       props=props, residual=excluded, kind="MACRO", editable=writable,
                       metadata_editable=bool(definition), macro_binding={"resource_id": uid, **block})
            continue
        if resource.kind == "source":
            group_name = uid.split(".")[2]
            group_uid = f"source_group.{resource.package}.{group_name}"
            if group_uid not in resources and not any(r["values"].get("Resource ID") == group_uid for r in sheet["rows"]):
                parent = project.resources.get(group_uid)
                summary = {"Type": "SOURCE", "Path": resource.model_path, "Name": group_name, "Resource ID": group_uid, "Package": resource.package,
                           "Source File": resource.source_file}
                if parent:
                    summary.update({"Description": parent.properties.get("description", ""), "Database": parent.properties.get("database", ""),
                                    "Schema": parent.properties.get("schema", "")})
                record(sheet, summary, kind="SOURCE", editable=False)
        values = {h: "" for h in sheet["headers"] if h != ROW_ID}
        kind = "SOURCE" if resource.kind == "source_group" else "MACRO" if macro else "TABLE"
        values.update({"Name": resource.name, "Description": row["description"], "Resource ID": uid, "Package": resource.package,
                       "Path": resource.model_path, "Source File": resource.source_file,
                       "Status": row["status"], "Reason": row["reason"]})
        if "Type" in values:
            values["Type"] = kind
        if macro:
            values["Path"] = resource.model_path
            values["Expression"] = row["sql"]
            values["Properties File"] = resource.property_path.relative_to(project.root).as_posix() if resource.property_path else ""
        elif not source:
            values["Authored SQL"] = row["sql"]
        authored = json.loads(row["properties"])
        authored_meta = authored.get("meta", authored.get("config", {}).get("meta", {}))
        if "Key" in values and isinstance(authored_meta, dict) and "key" in authored_meta:
            value = authored_meta["key"]
            values["Key"] = value if isinstance(value, str) else json_text(value)
        props, excluded = metadata(values, authored, source=source)
        metadata_editable = bool(resource.property_path) or resource.kind in {"model", "seed", "snapshot"}
        fields = {"Description": "description"} if metadata_editable else {}
        if resource.kind in {"model", "snapshot", "macro"} and resource.path and resource.path.suffix == ".sql":
            fields["Expression" if macro else "Authored SQL"] = "sql"
        level = 1 if resource.kind == "source" else 0
        record(sheet, values, target=["resources", uid], fields=fields, props=props, residual=excluded,
               kind=kind, level=level, editable=writable, metadata_editable=metadata_editable)

        parsed = None
        if resource.kind == "model" and resource.source_file.endswith(".sql"):
            try:
                parsed = parse_model(project, resource.code, uid, expand=expand, partial=True)
            except SpecError:
                pass  # Coverage/reason and full authored source remain available.
        output_columns = columns.get(uid, [])
        calls = macro_calls(row["sql"]) if resource.kind == "model" and resource.source_file.endswith(".sql") else []
        generated = expand and bool(calls)
        if calls:
            for call in model_macro_calls(project, row["sql"], uid):
                if call.sql is not None and (expand or call.single_column):
                    continue
                record(sheet, {"Type": "TEMPLATE", "Name": call.name or "TEMPLATE", "Expression": call.raw,
                               "Reason": call.reason},
                       target=["resources", uid], fields={"Expression": "sql"}, kind="TEMPLATE", level=1,
                       editable=writable, metadata_editable=False,
                       template_binding={"resource_id": uid, "start": call.start, "end": call.end})
        if parsed:
            for name, path, query in query_scopes(parsed.tree):
                output = not path
                supported = editable_select(query)
                scope_values = {"Type": "OUTPUT" if output else "STEP", "Name": name,
                                "Expression": clauses_text(query, parsed, project.dialect) if isinstance(query, exp.Select) else render(query, parsed, project.dialect).strip(),
                                "Distinct": "true" if query.args.get("distinct") else ""}
                scope = {"resource_id": uid, "path": path}
                record(sheet, scope_values, kind=scope_values["Type"], level=1, scope=scope,
                       fields={"Expression": "clauses", "Distinct": "distinct"} if supported and not generated and not parsed.opaque_macros else {}, editable=writable)
                if output:
                    continue
                for index, projection in enumerate(query.selects):
                    if contains_opaque(projection, parsed):
                        continue
                    expression = projection.this if isinstance(projection, exp.Alias) else projection
                    can_edit = supported and not projection.is_star and bool(projection.output_name)
                    record(sheet, {"Type": "COLUMN", "Name": projection.output_name or "*",
                                   "Expression": render(expression, parsed, project.dialect).strip().rstrip(";")},
                           kind="STEP COLUMN", level=2, scope={**scope, "projection": index, "column": projection.output_name},
                           fields={"Expression": "expression"} if can_edit and not generated else {}, editable=writable)
        elif not source and not macro:
            record(sheet, {"Type": "OUTPUT", "Name": "OUTPUT", "Expression": "", "Reason": row["reason"], "Status": row["status"]}, kind="OUTPUT", level=1)

        for col in output_columns:
            values = {h: "" for h in sheet["headers"] if h != ROW_ID}
            values.update({"Type": "COLUMN", "Name": col["column"], "Description": col["description"], "Data Type": col["data_type"], "Status": col["status"]})
            if "Expression" in values:
                values["Expression"] = col["expression"]
            props, excluded = metadata(values, json.loads(col["properties"]), source=source, column=True)
            fields = {"Description": "description", "Data Type": "data_type"}
            if parsed and not generated and isinstance(parsed.tree, exp.Select) and not any(p.is_star for p in parsed.tree.selects):
                if len([p for p in parsed.tree.selects if p.output_name == col["column"] and not contains_opaque(p, parsed)]) == 1:
                    fields["Expression"] = "expression"
            record(sheet, values, target=["columns", uid, col["column"]], fields=fields, props=props,
                   residual=excluded, level=2, editable=writable)

    # SOURCE summaries precede tables, not alphabetic resource-name order.
    for sheet in sheets:
        if sheet["category"] == "Sources":
            sheet["rows"].sort(key=lambda r: ((r["target"][1] if r["target"] else r["values"]["Resource ID"]).split(".")[2], 0 if r["kind"] == "SOURCE" else 1))
    order = {"Models": 0, "Snapshots": 1, "Seeds": 2, "Sources": 3, "Macros": 4}
    sheets.sort(key=lambda s: order[s["category"]])
    config_sheet = {"name": "Configuration", "headers": ["Scope", "Config", "Source File", ROW_ID], "rows": [], "category": "Config"}
    sheets.append(config_sheet)

    def config_scopes(value, path):
        if not isinstance(value, dict):
            return
        authored = scope_config(value)
        if authored:
            record(config_sheet, {"Scope": ".".join(path), "Config": json_text(authored), "Source File": "dbt_project.yml"},
                   kind="CONFIG", fields={"Config": "config"}, scope={"config_path": path})
        for key, child in value.items():
            if not key.startswith("+") and isinstance(child, dict):
                config_scopes(child, path + [key])

    for section in ("models", "seeds", "snapshots"):
        if section in project.authored:
            config_scopes(project.authored[section], [section])
    return sheets
