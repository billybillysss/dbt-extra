"""Hierarchical dbt review presentation and reversible cell-to-source bindings.

The flat review tables remain the import contract. This module projects them into
human-readable sheets; extra SQL/config bindings always address authored nodes.
"""

from __future__ import annotations

import copy
import io
import json
import math
import re
from xml.etree import ElementTree as ET

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.utils import get_column_letter
from openpyxl.writer.theme import theme_xml
from sqlglot import exp

from dbt_extra.project.properties import scope_config
from dbt_extra.sql.macros import macro_calls, parse_model, classify_calls, contains_opaque
from dbt_extra.sql.jinja import macro_blocks
from dbt_extra.sql.shorthand import display, restore, call_name, output_spans
from dbt_extra.sql.renderer import render
from dbt_extra.sql.scopes import query_scopes, editable_select, clauses_text
from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import literal, mapping
from dbt_extra.review.contract import EDITABLE, HEADERS, LEGEND, cell_text, structured


MODEL_HEADERS = ["Type", "Path", "Name", "Distinct", "Key",
                 "Expression", "Data Type", "Description", "Config", "Constraints", "Tests", "Meta"]
SOURCE_HEADERS = ["Type", "Path", "Name", "Database", "Schema", "Identifier", "Loader", "Data Type",
                  "Source Data Type", "Description", "Config", "Tests", "Meta", "Properties"]
MACRO_HEADERS = ["Path", "Name", "Expression", "Description", "Properties", "Properties File"]
CONTEXT_HEADERS = ["Resource ID", "Package", "Source File", "Status", "Reason"]
ROW_ID = "_extra_row_id"

# Forest + Paper: https://bigexcelenergy.com/excel-dashboard-color-palette/
# OUTPUT is a derived pale-sage tint; all column surfaces stay pure white.
PALETTE = {"canvas": "F7F8F5", "surface": "FFFFFF", "text": "1F2723", "muted": "65726A",
           "accent": "2F7D4F", "support": "2B5F75", "output": "EAF2ED"}
CHART_COLORS = ("2F7D4F", "2B5F75", "B56727", "6B3FA0", "007C78", "B6424E")


def forest_paper_theme():
    """Embed matching Office theme slots for Excel's theme color picker."""
    namespace = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ET.register_namespace("a", namespace)
    root = ET.fromstring(theme_xml)
    root.set("name", "Forest + Paper")
    scheme = root.find(f".//{{{namespace}}}clrScheme")
    scheme.set("name", "Forest + Paper")
    colors = {"dk1": PALETTE["text"], "lt1": PALETTE["surface"], "dk2": PALETTE["support"],
              "lt2": PALETTE["canvas"], "hlink": PALETTE["accent"], "folHlink": PALETTE["muted"],
              **{f"accent{i}": color for i, color in enumerate(CHART_COLORS, 1)}}
    for slot in scheme:
        name = slot.tag.rsplit("}", 1)[1]
        slot.clear()
        ET.SubElement(slot, f"{{{namespace}}}srgbClr", val=colors[name])
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def workbook_for(project, document, tables, baseline, *, expand=False):
    """Build path-grouped sheets and a hidden, versioned presentation baseline."""
    resources = {r["resource_id"]: r for r in tables["resources"]}
    columns = {}
    for row in tables["columns"]:
        columns.setdefault(row["resource_id"], []).append(row)
    sheets = []
    groups = {}
    used_names = {"README", "configuration", "_baseline"}

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
            values[header] = (str(props[key]) if header in {"Database", "Schema", "Identifier", "Loader"} else text(props[key])) if key in props else ""
            bindings[header] = key
        excluded = set(bindings.values())
        values["Properties"] = text({k: v for k, v in props.items() if k not in excluded})
        return bindings, excluded

    # Flat resources remain the import contract; presentation joins documentation
    # by actual macro name, not by the SQL filename (which may hold many macros).
    definitions = {(project.resources[uid].package, row["name"]): uid
                   for uid, row in resources.items() if project.resources[uid].kind == "macro_definition"}
    macros = {}
    matched = set()
    names = set()
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
            values["Key"] = value if isinstance(value, str) else text(value)
        props, excluded = metadata(values, authored, source=source)
        metadata_editable = bool(resource.property_path) or resource.kind in {"model", "seed", "snapshot"}
        fields = {"Description": "description"} if metadata_editable else {}
        if resource.kind in {"model", "snapshot", "macro"} and resource.path and resource.path.suffix == ".sql":
            fields["Expression" if macro else "Authored SQL"] = "sql"
        # Sources are grouped under their SOURCE row even with a table-only selector.
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
            for call in classify_calls(project, row["sql"], uid):
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
                    continue  # Final columns use analysis metadata, not inferred CTE metadata.
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
            record(config_sheet, {"Scope": ".".join(path), "Config": text(authored), "Source File": "dbt_project.yml"},
                   kind="CONFIG", fields={"Config": "config"}, scope={"config_path": path})
        for key, child in value.items():
            if not key.startswith("+") and isinstance(child, dict):
                config_scopes(child, path + [key])

    for section in ("models", "seeds", "snapshots"):
        if section in project.authored:
            config_scopes(project.authored[section], [section])

    baseline = {**baseline, "workbook": {"version": 1, "sheets": sheets}}
    book = Workbook()
    book.loaded_theme = forest_paper_theme()
    legend = book.active
    legend.title = "README"
    for row in [
        ["dbt-extra dbt review", "Native dbt SQL/YAML remain authoritative. Sheets follow package and native model/folder paths; no dbt-extra defaults or layer/domain registry."],
        ["Hierarchy", "TABLE > STEP / OUTPUT > COLUMN; SOURCE > TABLE > COLUMN. Collapse outlines to scan tables."],
        ["Editable cells", "Unlocked cells: authored metadata, supported SELECT clauses, Distinct and projection expressions. Context is read-only."],
        ["Structured metadata", 'Config / Meta / Properties: JSON objects. Tests / Constraints: JSON arrays. Example Tests: ["not_null"]. Blank removes the authored field.'],
        ["Example (not imported)", 'COLUMN customer_id: Description = Customer identifier; Data Type = bigint; Tests = ["not_null", "unique"].'],
        ["SQL edits", "Edit supported STEP/OUTPUT clauses (FROM/JOIN/WHERE/GROUP BY/etc.) or column expressions. Keep aliases in Name unchanged. Distinct: true or blank."],
        ["Full source", "Authored SQL columns are hidden to keep the hierarchy compact; unhide to edit full source instead of structured SQL cells. Macro Expression edits only the named macro; documentation writes to Properties File."],
        ["Configuration", 'Edit authored package/folder Config at its original dbt_project.yml Scope, e.g. models.jaffle_shop. Empty scopes are omitted. Preserve + prefixes, e.g. {"+materialized": "view"}. Inherited config is not flattened into authored fields.'],
        ["Paths and templates", "Path is the project-relative folder, e.g. models/slv. Simple references use ref.model / source.group.table; calls use macro.name(arguments). Imports restore dbt Jinja. Complex templates retain their syntax."],
        ["Macro columns", "Known single-column scalar, aggregate and window calls stay COLUMN expressions using macro.name(...). Each call is classified independently; only unresolved or unexpanded multi-column/clause output stays TEMPLATE."],
        ["Package", "Read-only owning dbt project/package, e.g. jaffle_shop. Distinguishes same-named resources in different packages; it is not a folder path."],
        ["CASE template example", "CASE WHEN amount > 0 THEN macro.round_money('amount') ELSE 0 END. Supported scalar calls remain editable column expressions; opaque calls stay TEMPLATE rows."],
        ["Macro expansion", "export --expand derives COLUMN mappings from resolved macro SQL, without extra TEMPLATE rows. Generated expressions/clauses are read-only; edit Authored SQL or the macro definition. Unresolved output stays TEMPLATE with its reason; no column count is guessed."],
        ["Safety", "Keep all rows, sheets and the hidden baseline/identities. No additions, deletions, renames or moves. Stale files, formulas and read-only edits are rejected."],
        ["Limitations", "Opaque Jinja and unsupported query shapes stay visible but cannot be structurally rewritten. Full source receives structural checks, not dbt execution. Run dbt validation independently."],
    ]:
        legend.append(row)
    legend.column_dimensions["A"].width = 26
    legend.column_dimensions["B"].width = 112
    legend.sheet_view.showGridLines = False
    for row in legend:
        legend.row_dimensions[row[0].row].height = 44
        for cell in row:
            cell.data_type = "s"
            cell.font = Font(name="Arial", size=10, color=PALETTE["accent"] if cell.column == 1 else PALETTE["text"], bold=cell.column == 1)
            cell.fill = PatternFill("solid", fgColor=PALETTE["canvas"] if cell.column == 1 else PALETTE["surface"])
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for spec in sheets:
        write_sheet(book, spec)
    hidden = book.create_sheet("_baseline")
    raw = text(baseline)
    for offset in range(0, len(raw), 30000):
        hidden.append([raw[offset:offset + 30000]])
        hidden.cell(hidden.max_row, 1).data_type = "s"
        hidden.cell(hidden.max_row, 1).font = Font(name="Arial", size=10)
    hidden.sheet_state = "veryHidden"
    stream = io.BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


def write_sheet(book, spec):
    sheet = book.create_sheet(spec["name"])
    headers = spec["headers"]
    sheet.append(headers)
    widths = {"Type": 13, "Path": 30, "Name": 30, "Distinct": 10, "Key": 14,
              "Expression": 80, "Data Type": 20, "Description": 48,
              "Config": 45, "Constraints": 32, "Tests": 34, "Meta": 36, "Properties": 44, "Authored SQL": 80,
              "Scope": 48, "Reason": 48, "Source File": 42}
    for index, header in enumerate(headers, 1):
        dimension = sheet.column_dimensions[get_column_letter(index)]
        dimension.width = widths.get(header, 24)
        dimension.hidden = header in {ROW_ID, "Authored SQL"}
    for item in spec["rows"]:
        values = {**item["values"], ROW_ID: item["id"]}
        if any(len(str(value)) > 32767 for value in values.values()):
            raise SpecError(f"XLSX cell limit exceeded in {spec['name']}; use CSV or JSON for large SQL")
        sheet.append([values.get(h, "") for h in headers])
        row_number = sheet.max_row
        sheet.row_dimensions[row_number].outlineLevel = item["level"]
        kind = item["kind"]
        dark = kind in {"TABLE", "SOURCE", "MACRO"}
        fill = (PALETTE["support"] if kind == "TABLE" and spec["category"] == "Snapshots" else
                PALETTE["accent"] if dark else PALETTE["output"] if kind == "OUTPUT" else
                PALETTE["canvas"] if kind == "STEP" else PALETTE["surface"])
        editable_headers = set(item["fields"]) | (set(item["props"]) | {"Properties"} if item["target"] and item["metadata_editable"] else set())
        height = 1
        for cell, header in zip(sheet[row_number], headers, strict=True):
            editable = item["editable"] and header in editable_headers
            cell.data_type = "s"
            context = header in CONTEXT_HEADERS + [ROW_ID, "Path", "Key"]
            color = PALETTE["surface"] if dark else PALETTE["accent"] if editable else PALETTE["muted"] if context else PALETTE["text"]
            cell.font = Font(name="Arial", size=10, color=color, bold=kind in {"TABLE", "SOURCE", "MACRO", "STEP", "OUTPUT"})
            cell.fill = PatternFill("solid", fgColor=fill)
            cell.alignment = Alignment(vertical="top", wrap_text=True, indent=item["level"] if header == "Name" else 0)
            cell.protection = Protection(locked=not editable)
            if header not in {ROW_ID, "Authored SQL"}:
                width = max(8, widths.get(header, 24) - 2)
                height = max(height, sum(max(1, math.ceil(len(line) / width)) for line in str(cell.value or "").split("\n")))
        sheet.row_dimensions[row_number].height = min(150, max(24, 14 * height + 8))
    for cell in sheet[1]:
        cell.data_type = "s"
        cell.font = Font(name="Arial", size=10, bold=True, color=PALETTE["surface"])
        cell.fill = PatternFill("solid", fgColor=PALETTE["text"])
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 30
    sheet.freeze_panes = "D2" if "Type" in headers else "C2"
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.outlinePr.summaryRight = False
    sheet.sheet_properties.outlinePr.summaryBelow = False
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.sheet_properties.tabColor = PALETTE["support"] if spec["category"] == "Config" else PALETTE["accent"]
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers) - 1)}{sheet.max_row}"
    sheet.print_title_rows = "1:1"
    visible_end = len(headers) - (2 if "Authored SQL" in headers else 1)
    sheet.print_area = f"A1:{get_column_letter(visible_end)}{sheet.max_row}"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0


def read_hierarchy(book, baseline, edits):
    """Validate every visible cell, then reconstruct flat tables and scoped edits."""
    layout = baseline["workbook"]
    if layout.get("version") != 1:
        raise SpecError("Unsupported workbook layout; re-export")
    expected_sheets = {s["name"] for s in layout["sheets"]} | {"README", "_baseline"}
    if set(book.sheetnames) != expected_sheets:
        raise SpecError("Review sheets changed; keep the original sheets and re-export for new resources")
    tables = copy.deepcopy(baseline["tables"])
    targets = {("resources", r["resource_id"]): r for r in tables["resources"]}
    targets.update({("columns", r["resource_id"], r["column"]): r for r in tables["columns"]})
    macro_updates = {}
    template_updates = {}
    for sheet in layout["sheets"]:
        rows = iter(book[sheet["name"]].iter_rows())
        if [c.value for c in next(rows, ())] != sheet["headers"]:
            raise SpecError(f"Unexpected headers in {sheet['name']}")
        original = {r["id"]: r for r in sheet["rows"]}
        seen = set()
        for cells in rows:
            if all(c.value is None for c in cells):
                continue
            if any(c.data_type in {"f", "e"} for c in cells):
                raise SpecError("Formula and Excel error cells are not accepted in review data")
            values = {h: cell_text(c.value) for h, c in zip(sheet["headers"], cells, strict=True)}
            identity = values.pop(ROW_ID)
            if identity not in original or identity in seen:
                raise SpecError(f"Unknown or duplicate review row: {sheet['name']} ({identity})")
            seen.add(identity)
            previous = original[identity]
            changed = {h: v for h, v in values.items() if v != previous["values"].get(h, "")}
            allowed = set(previous["fields"]) | (set(previous["props"]) | {"Properties"} if previous["target"] and previous["metadata_editable"] else set())
            if changed and (not previous["editable"] or changed.keys() - allowed):
                raise SpecError(f"Read-only field changed: {sheet['name']} ({identity})")
            if not changed:
                continue
            if "Expression" in changed and "original_expression" in previous and sheet["category"] not in {"Macros", "Config"}:
                changed["Expression"] = restore(changed["Expression"], previous["original_expression"])
            if previous["scope"]:
                edits.append({**previous["scope"], "changes": {previous["fields"][h]: v for h, v in changed.items()}})
                continue
            template = previous.get("template_binding")
            if template:
                candidate = changed["Expression"]
                spans = list(output_spans(candidate))
                if len(spans) != 1 or spans[0][0] != 0 or spans[0][1] != len(candidate) or not macro_calls(candidate):
                    raise SpecError("Expected one authored macro template call")
                template_updates.setdefault(template["resource_id"], []).append((template, candidate))
                continue
            binding = previous.get("macro_binding")
            if binding:
                edits.append({"macro_resource_ids": [binding["resource_id"], previous["target"][1]]})
                if "Expression" in changed:
                    candidate = changed["Expression"]
                    blocks = macro_blocks(candidate, binding["name"])
                    if (len(blocks) != 1 or blocks[0]["name"] != binding["name"]
                            or candidate[:blocks[0]["start"]].strip() or candidate[blocks[0]["end"]:].strip()):
                        raise SpecError(f"Keep the original named macro: {binding['name']}")
                    macro_updates.setdefault(binding["resource_id"], []).append((binding, candidate))
            target = targets[tuple(previous["target"])]
            for header, field in previous["fields"].items():
                if header in changed and not (binding and header == "Expression"):
                    target[field] = changed[header]
            props = json.loads(target["properties"])
            if "Properties" in changed:
                dedicated = {"name", "description", "data_type"} if previous["target"][0] == "columns" else {"name", "description", "columns", "tables"}
                residual = structured(changed["Properties"], "Properties", set(previous["residual"]) | dedicated)
                props = {k: v for k, v in props.items() if k in previous["residual"]}
                props.update(residual)
            for header, key in previous["props"].items():
                if header not in changed:
                    continue
                value = changed[header]
                if not value:
                    props.pop(key, None)
                elif header in {"Database", "Schema", "Identifier", "Loader"}:
                    props[key] = value
                else:
                    try:
                        parsed = json.loads(value)
                        literal(parsed, header)
                    except ValueError as exc:
                        raise SpecError(f"{header}: invalid JSON: {exc}") from exc
                    if header in {"Config", "Meta"}:
                        mapping(parsed, header)
                    elif not isinstance(parsed, list):
                        raise SpecError(f"{header}: expected a JSON array")
                    props[key] = parsed
            target["properties"] = text(props)
        if seen != set(original):
            raise SpecError(f"Rows were removed from {sheet['name']}; deletion is not supported")
    for uid, updates in macro_updates.items():
        target = targets[("resources", uid)]
        code = target["sql"]
        for binding, candidate in sorted(updates, key=lambda update: update[0]["start"], reverse=True):
            code = code[:binding["start"]] + candidate + code[binding["end"]:]
        target["sql"] = code
    for uid, updates in template_updates.items():
        target = targets[("resources", uid)]
        original = next(r["sql"] for r in baseline["tables"]["resources"] if r["resource_id"] == uid)
        if target["sql"] != original:
            raise SpecError(f"Edit SQL or template calls, not both: {uid}")
        code = original
        for binding, candidate in sorted(updates, key=lambda update: update[0]["start"], reverse=True):
            code = code[:binding["start"]] + candidate + code[binding["end"]:]
        target["sql"] = code
        edits.append({"template_resource_id": uid})
    return tables


def read_workbook(path, *, workbook_edits=None):
    """Read hierarchical reviews and previously exported flat dbt workbooks."""
    book = load_workbook(path, data_only=False, read_only=True)
    try:
        if "_baseline" not in book.sheetnames:
            raise SpecError("Workbook has no dbt-extra baseline; re-export it")
        raw = "".join(str(row[0]) for row in book["_baseline"].iter_rows(values_only=True) if row[0])
        baseline = json.loads(raw)
        if "workbook" in baseline:
            return read_hierarchy(book, baseline, workbook_edits if workbook_edits is not None else []), baseline
        tables = {}
        for name, headers in HEADERS.items():
            if name not in book.sheetnames:
                raise SpecError(f"Missing sheet: {name}")
            rows = iter(book[name].iter_rows())
            if [c.value for c in next(rows, ())] != headers:
                raise SpecError(f"Unexpected headers in {name}")
            items = []
            for row in rows:
                if all(c.value is None for c in row):
                    continue
                if any(c.data_type in {"f", "e"} for c in row):
                    raise SpecError("Formula and Excel error cells are not accepted in review data")
                items.append({h: cell_text(c.value) for h, c in zip(headers, row, strict=True)})
            tables[name] = items
        return tables, baseline
    finally:
        book.close()


def workbook(tables, baseline):
    """Serialize the flat dbt layout for consumers of existing review tables."""
    book = Workbook()
    legend = book.active
    legend.title = "README"
    for row in LEGEND:
        legend.append(row)
    legend.column_dimensions["A"].width = 26
    legend.column_dimensions["B"].width = 110
    for row in legend:
        for cell in row:
            cell.font = Font(name="Arial", size=11)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        legend.row_dimensions[row[0].row].height = 34
    for name, headers in HEADERS.items():
        sheet = book.create_sheet(name)
        sheet.append(headers)
        for item in tables[name]:
            values = [item.get(h, "") for h in headers]
            if any(len(str(value)) > 32767 for value in values):
                raise SpecError(f"XLSX cell limit exceeded in {name}; use CSV or JSON for large SQL")
            sheet.append(values)
        sheet.freeze_panes = "D2"
        sheet.auto_filter.ref = sheet.dimensions
        for row in sheet:
            for cell in row:
                cell.data_type = "s"
                editable = cell.row > 1 and headers[cell.column - 1] in EDITABLE[name]
                cell.font = Font(name="Arial", size=10, color="175CD3" if editable else "344054", bold=cell.row == 1)
                cell.fill = PatternFill("solid", fgColor="EAF2FF" if editable else "F2F4F7")
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.protection = Protection(locked=not editable)
        for index, header in enumerate(headers, 1):
            sheet.column_dimensions[sheet.cell(1, index).column_letter].width = 60 if header in {"sql", "properties", "expression", "reason"} else 28
    hidden = book.create_sheet("_baseline")
    raw = text(baseline)
    for offset in range(0, len(raw), 30000):
        hidden.append([raw[offset:offset + 30000]])
        hidden.cell(hidden.max_row, 1).data_type = "s"
        hidden.cell(hidden.max_row, 1).font = Font(name="Arial", size=10)
    hidden.sheet_state = "veryHidden"
    stream = io.BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()
