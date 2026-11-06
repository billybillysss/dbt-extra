"""Resolve inspection-only physical relations without executing dbt or profiles."""

from sqlglot import exp, parse_one
from sqlglot.errors import ErrorLevel, SqlglotError

from dbt_extra.project.references import resolve_ref
from dbt_extra.sql.renderer import reference_aliases


def literal(value):
    return isinstance(value, str) and bool(value.strip()) and not any(
        marker in value for marker in ("{{", "{%", "{#"))


def table_from_parts(parts, quoting):
    if not isinstance(quoting, dict) or any(type(v) is not bool for v in quoting.values()):
        return None
    return exp.Table(**{key: exp.to_identifier(value, quoted=quoting.get(component))
                        for component, key, value in zip(
                            ("database", "schema", "identifier"), ("catalog", "db", "this"), parts)
                        if value is not None})


def manifest_relation(project, resource):
    node = resource.node
    if resource.stale or not node or resource.config.get("materialized") == "ephemeral":
        return None
    # Do not reuse relation evidence after literal authored naming config changes.
    authored = {**resource.inherited_config, **resource.properties.get("config", {}), **resource.inline_config}
    for key in ("schema", "database", "alias", "materialized"):
        value = authored.get(key)
        if literal(value) and node.get("config", {}).get(key) != value:
            return None
    raw = node.get("relation_name")
    if literal(raw):
        try:
            table = parse_one(raw, read=project.dialect, into=exp.Table, error_level=ErrorLevel.RAISE)
            if (isinstance(table, exp.Table) and isinstance(table.this, exp.Identifier)
                    and all(isinstance(v, exp.Identifier) for v in table.args.values() if v is not None)):
                return table
        except (SqlglotError, ValueError):
            pass
        return None
    parts = (node.get("database"), node.get("schema"), node.get("identifier") or node.get("alias"))
    if all(literal(p) for p in parts[1:]) and (parts[0] is None or literal(parts[0])):
        return table_from_parts(parts, node.get("quoting", project.authored.get("quoting", {})))
    return None


def source_relation(project, resource, ref):
    group = project.resources.get(f"source_group.{resource.package}.{ref.args[0]}")
    if group is None:
        return manifest_relation(project, resource)
    properties = {**group.properties, **resource.properties}
    parts = (properties.get("database"), properties.get("schema") or ref.args[0],
             properties.get("identifier") or resource.name)
    group_quoting, table_quoting = group.properties.get("quoting", {}), resource.properties.get("quoting", {})
    if not isinstance(group_quoting, dict) or not isinstance(table_quoting, dict):
        return None
    quoting = {**group_quoting, **table_quoting}
    if any(type(v) is not bool for v in quoting.values()):
        return None
    evidence = manifest_relation(project, resource)
    if evidence is not None:
        # Literal authored names take precedence over stale source YAML evidence.
        for component, key, value in zip(("database", "schema", "identifier"), ("catalog", "db", "this"), parts):
            identifier = evidence.args.get(key)
            if ((literal(value) and (identifier is None or identifier.name != value))
                    or (component in quoting and identifier is not None
                        and bool(identifier.args.get("quoted")) != quoting[component])):
                evidence = None
                break
    if evidence is not None:
        return evidence
    if not all(literal(p) for p in parts[1:]) or not (parts[0] is None or literal(parts[0])):
        return None
    return table_from_parts(parts, quoting)


def resolve_physical_relations(project, tree, refs):
    """Replace only surviving table references; leave unresolved templates visible."""
    reference_aliases(tree, refs)
    issues, reported = [], set()
    for table in tree.find_all(exp.Table):
        ref = refs.get(table.name)
        if ref is None:
            continue
        resource = (project.resources.get(table.meta.get("extra_owner")) if ref.kind == "this"
                    else resolve_ref(project, ref))
        relation = None
        if resource is not None:
            relation = (source_relation(project, resource, ref) if ref.kind == "source"
                        else manifest_relation(project, resource))
        if relation is None:
            uid = resource.id if resource else ref.text
            if uid not in reported:
                issues.append({"resource_id": uid, "reason": "Physical relation unavailable; dbt template retained. "
                               "Supply a current manifest for the intended target (for example, from dbt parse)."})
                reported.add(uid)
            continue
        for key in ("this", "db", "catalog"):
            value = relation.args.get(key)
            table.set(key, value.copy() if value is not None else None)
    remaining = {t.name for t in tree.find_all(exp.Table)}
    return {token: ref for token, ref in refs.items() if token in remaining}, issues
