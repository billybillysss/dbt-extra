"""Portable dbt property shapes and authored configuration inheritance."""

from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import mapping


def validate_properties(value, context):
    mapping(value, context)
    if not isinstance(value.get("name"), str) or not value["name"]:
        raise SpecError(f"{context}: properties require a nonempty name")
    for key in ("description", "data_type"):
        if key in value and not isinstance(value[key], str):
            raise SpecError(f"{context}.{key}: expected text")
    if "config" in value:
        mapping(value["config"], f"{context}.config")
    for key in ("tests", "data_tests", "constraints", "columns"):
        if key in value and not isinstance(value[key], list):
            raise SpecError(f"{context}.{key}: expected a list")
    names = []
    for column in value.get("columns", []):
        validate_properties(column, f"{context}.columns")
        names.append(column["name"])
    if len(set(names)) != len(names):
        raise SpecError(f"{context}: duplicate column properties")


def scope_config(value):
    """Direct authored dbt settings, excluding nested package/folder scopes."""
    return {k: v for k, v in value.items() if k.startswith("+") or not isinstance(v, dict)}


def inherited_config(authored, kind, package, relative):
    tree = authored.get({"model": "models", "snapshot": "snapshots", "seed": "seeds", "macro": "macros"}[kind], {})
    if not isinstance(tree, dict):
        return {}
    result = {k.lstrip("+"): v for k, v in scope_config(tree).items()}
    for component in [package, *relative.with_suffix("").parts]:
        tree = tree.get(component, {})
        if not isinstance(tree, dict):
            break
        result.update({k.lstrip("+"): v for k, v in scope_config(tree).items()})
    return result
