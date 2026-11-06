"""Validate XLSX review cells and reconstruct flat tables and authored edits."""

import copy
import json

from openpyxl import load_workbook

from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import literal, mapping
from dbt_extra.review.contract import cell_text, json_text, structured
from dbt_extra.review.shorthand import restore
from dbt_extra.review.xlsx.layout import ROW_ID
from dbt_extra.sql.templates.macros import macro_calls
from dbt_extra.sql.templates.syntax import macro_blocks, output_spans


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
            target["properties"] = json_text(props)
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
    book = load_workbook(path, data_only=False, read_only=True)
    try:
        if "_baseline" not in book.sheetnames:
            raise SpecError("Workbook has no dbt-extra baseline; re-export it")
        raw = "".join(str(row[0]) for row in book["_baseline"].iter_rows(values_only=True) if row[0])
        baseline = json.loads(raw)
        if "workbook" not in baseline:
            raise SpecError("Unsupported workbook layout; re-export")
        return read_hierarchy(book, baseline, workbook_edits if workbook_edits is not None else []), baseline
    finally:
        book.close()
