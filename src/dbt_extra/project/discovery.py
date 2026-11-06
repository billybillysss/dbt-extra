"""Discover authored dbt files and attach optional artifact evidence."""

from pathlib import Path

from jinja2 import nodes as jinja_nodes

from dbt_extra.errors import SpecError
from dbt_extra.files.paths import within
from dbt_extra.files.yaml import load_yaml
from dbt_extra.project.properties import inherited_config, validate_properties
from dbt_extra.project.resources import Resource
from dbt_extra.sql.templates.syntax import validate_template


def discover(project):
    nodes = {**project.manifest.get("nodes", {}), **project.manifest.get("sources", {})}
    by_file = {}
    for uid, node in nodes.items():
        if node.get("package_name") == project.name:
            by_file.setdefault(node.get("original_file_path"), []).append((uid, node))
    for kind, roots, extensions in (
        ("model", project.model_roots, {".sql", ".py"}),
        ("snapshot", project.snapshot_roots, {".sql"}),
        ("seed", project.seed_roots, {".csv"}),
        ("macro", project.macro_roots, {".sql"}),
    ):
        for root in roots:
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.suffix not in extensions:
                    continue
                within(project.root, str(path))
                relative = path.relative_to(project.root).as_posix()
                matches = [(uid, n) for uid, n in by_file.get(relative, []) if n.get("resource_type") == kind]
                if len(matches) > 1:
                    raise SpecError(f"Ambiguous artifact resources for {relative}")
                uid, node = matches[0] if matches else (f"{kind}.{project.name}.{path.stem}", {})
                if kind == "macro":
                    uid = f"macro_file.{project.name}.{relative}"
                if uid in project.resources:
                    raise SpecError(f"Duplicate dbt resource {uid}; provide a manifest for versioned models")
                folder = path.parent.relative_to(project.root).as_posix()
                project.contents[path] = path.read_bytes()
                code = project.contents[path].decode("utf-8") if kind != "seed" else ""
                resource = Resource(uid, node.get("name", path.stem), kind, project.name, path, relative, folder, code, node=node)
                resource.inherited_config = inherited_config(project.authored, kind, project.name, path.relative_to(root))
                if kind == "model" and path.suffix == ".sql":
                    template = validate_template(code, relative)
                    for call in template.find_all(jinja_nodes.Call):
                        if isinstance(call.node, jinja_nodes.Name) and call.node.name == "config":
                            for kw in call.kwargs:
                                try:
                                    resource.inline_config[kw.key] = kw.value.as_const()
                                except jinja_nodes.Impossible:
                                    pass
                project.resources[uid] = resource
                if node.get("raw_code") is not None and node["raw_code"].replace("\r\n", "\n") != code.replace("\r\n", "\n"):
                    resource.stale = True
                    project.diagnostics.append({"resource_id": uid, "code": "SOURCE_CHANGED", "reason": "Authored code differs from manifest; compiled SQL is not used for source rewriting"})
    property_roots = set(project.model_roots + project.snapshot_roots + project.seed_roots + project.macro_roots)
    for path in sorted({p for root in property_roots for p in root.rglob("*") if p.suffix in {".yml", ".yaml"}}):
        within(project.root, str(path))
        project.contents[path] = path.read_bytes()
        document = load_yaml(path, project.contents)
        for key, kind in (("models", "model"), ("seeds", "seed"), ("snapshots", "snapshot"), ("macros", "macro_definition")):
            entries = document.get(key, [])
            if not isinstance(entries, list):
                raise SpecError(f"{path}: {key} must be a list")
            for index, entry in enumerate(entries):
                validate_properties(entry, str(path))
                candidates = [r for r in project.resources.values() if r.kind == kind and r.name == entry.get("name")]
                if not candidates and kind in {"snapshot", "macro_definition"}:
                    uid = f"{kind}.{project.name}.{entry['name']}"
                    relative = path.relative_to(project.root).as_posix()
                    resource = Resource(uid, entry["name"], kind, project.name, path, relative, path.parent.relative_to(project.root).as_posix())
                    project.resources[uid] = resource
                    candidates = [resource]
                for resource in candidates:
                    if resource.property_path:
                        raise SpecError(f"Duplicate properties for {resource.id}")
                    resource.properties, resource.property_path, resource.property_locator = entry, path, (key, index)
                    if entry.get("versions"):
                        project.diagnostics.append({"resource_id": resource.id, "code": "VERSIONED_PROPERTIES", "reason": "Version inheritance is read-only"})
        if not isinstance(document.get("sources", []), list):
            raise SpecError(f"{path}: sources must be a list")
        for i, group in enumerate(document.get("sources", [])):
            validate_properties(group, str(path))
            if not isinstance(group.get("name"), str) or not isinstance(group.get("tables", []), list):
                raise SpecError(f"{path}: sources require a name and tables list")
            relative = path.relative_to(project.root).as_posix()
            folder = path.parent.relative_to(project.root).as_posix()
            group_id = f"source_group.{project.name}.{group['name']}"
            if group_id in project.resources:
                raise SpecError(f"Duplicate source group {group['name']}")
            project.resources[group_id] = Resource(group_id, group["name"], "source_group", project.name, path, relative, folder,
                properties={k: v for k, v in group.items() if k != "tables"}, property_path=path, property_locator=("sources", i))
            for j, entry in enumerate(group.get("tables", [])):
                validate_properties(entry, str(path))
                uid = f"source.{project.name}.{group['name']}.{entry['name']}"
                if uid in project.resources:
                    raise SpecError(f"Duplicate source {uid}")
                project.resources[uid] = Resource(uid, entry["name"], "source", project.name, path, relative, folder,
                    properties=entry, property_path=path, property_locator=("sources", i, "tables", j), node=nodes.get(uid, {}))
    # Package and manifest-only resources remain visible, but are not writable.
    for uid, node in sorted(nodes.items()):
        if uid in project.resources or node.get("resource_type") not in {"model", "source", "seed", "snapshot"}:
            continue
        relative = node.get("original_file_path", "")
        props = {"description": node.get("description", ""), "columns": list(node.get("columns", {}).values())}
        project.resources[uid] = Resource(uid, node.get("name", uid), node["resource_type"], node.get("package_name", ""),
            None, relative, Path(relative).parent.as_posix(), node.get("raw_code", ""), props, node=node)
