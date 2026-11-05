"""Fill missing metadata using shared analysis; never overwrite authored values."""

from __future__ import annotations

import copy

from sqlglot import exp

from dbt_extra.analysis import analyze
from dbt_extra.files.changes import ChangeSet, digest
from dbt_extra.sql.parser import parse_authored
from dbt_extra.errors import SpecError


def enrich(project, *, select=None, exclude=None, changes=None):
    project.require_dialect()
    changes = changes or ChangeSet(project.root)
    for path, data in project.contents.items():
        changes.watch(path, digest(data), check=True, external=not path.is_relative_to(project.root))
    report, cache, active = [], {}, set()

    def metadata(r):
        if r.id in cache:
            return cache[r.id]
        if r.id in active:
            return r.columns
        active.add(r.id)
        result = copy.deepcopy(r.columns)
        analysis = analyze(project, r)
        try:
            parsed = parse_authored(r.code, project.dialect, r.id)
            output = {p.output_name: p for p in parsed.tree.selects}
        except SpecError:
            parsed, output = None, {}
        for item in analysis["columns"]:
            name = item["name"]
            props = result.setdefault(name, {"name": name})
            if not props.get("data_type") and item.get("inferred_type"):
                props["data_type"] = item["inferred_type"]
            projection = output.get(name)
            expression = projection.this if isinstance(projection, exp.Alias) else projection
            # Only bare passthrough/renamed columns inherit a description. The
            # lineage relation must resolve uniquely; transformed values do not.
            if not props.get("description") and isinstance(expression, exp.Column):
                leaves = item["upstream_columns"]
                if len(leaves) == 1:
                    leaf = leaves[0]
                    upstream = project.resources.get(leaf["resource_id"])
                    if upstream:
                        inherited = metadata(upstream).get(leaf["column"], {}).get("description")
                        if inherited:
                            props["description"] = inherited
        active.remove(r.id)
        cache[r.id] = result
        return result

    for r in project.select(select, exclude, kinds={"model"}):
        if not r.path or r.path.suffix != ".sql" or r.properties.get("versions"):
            report.append({"resource_id": r.id, "reason": "Read-only or versioned metadata"})
            continue
        proposed = copy.deepcopy(r.properties)
        columns = proposed.setdefault("columns", [])
        by_name = {c["name"]: c for c in columns}
        for name, inferred in metadata(r).items():
            target = by_name.get(name)
            for key in ("data_type", "description"):
                if target and target.get(key):
                    continue
                if inferred.get(key):
                    if target is None:
                        target = {"name": name}
                        columns.append(target)
                        by_name[name] = target
                    target[key] = inferred[key]
                    report.append({"resource_id": r.id, "column": name, "property": key, "value": inferred[key]})
                else:
                    report.append({"resource_id": r.id, "column": name, "property": key, "reason": "Not safely inferable from available source metadata"})
        proposed.setdefault("name", r.name)
        if any("value" in item and item["resource_id"] == r.id for item in report):
            changes.properties(project, r, proposed)
    return changes, report
