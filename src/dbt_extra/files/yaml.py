"""Strict portable YAML loading and lossless mapping patches."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import yaml

from dbt_extra.errors import SpecError


class UniqueLoader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    pass


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str):
            raise SpecError("YAML mapping keys must be strings")
        if key in result:
            raise SpecError(f"duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)
UniqueLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in values if tag != "tag:yaml.org,2002:bool"]
    for key, values in UniqueLoader.yaml_implicit_resolvers.items()
}
UniqueLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.I), list("tTfF"))


def mapping(value: Any, context: str) -> dict:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise SpecError(f"{context}: expected a mapping with string keys")
    return value


def fields(value: dict, allowed: set, required: set, context: str) -> None:
    unknown, missing = value.keys() - allowed, required - value.keys()
    if unknown or missing:
        raise SpecError(f"{context}: unknown fields {sorted(map(str, unknown))}; missing fields {sorted(missing)}")


def text(value: Any, context: str, *, empty=False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise SpecError(f"{context}: expected a {'string' if empty else 'nonempty string'}")
    return value


def literal(value, context="configuration"):
    """Validate the portable, finite YAML/JSON literal subset recursively."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, list):
        for item in value:
            literal(item, context)
        return value
    if isinstance(value, dict):
        mapping(value, context)
        for item in value.values():
            literal(item, context)
        return value
    raise SpecError(f"{context}: expected finite configuration literals")


def load_yaml(path: Path, overrides: dict | None = None) -> dict:
    try:
        content = overrides[path] if overrides is not None and path in overrides else path.read_bytes()
        return mapping(yaml.load(content, Loader=UniqueLoader), str(path))
    except (OSError, yaml.YAMLError, UnicodeError) as exc:
        raise SpecError(f"{path}: {exc}") from exc


class LiteralDumper(getattr(yaml, "CSafeDumper", yaml.SafeDumper)):
    pass


def _string(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


LiteralDumper.add_representer(str, _string)


class IndentedDumper(yaml.SafeDumper):
    """Match portable boolean rules and indent nested sequences."""

    yaml_implicit_resolvers = UniqueLoader.yaml_implicit_resolvers

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, indentless=False)


def _indented_string(dumper, value):
    if "\u0085" in value:
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style='"')
    return _string(dumper, value)


IndentedDumper.add_representer(str, _indented_string)


def dump_yaml(value: dict, *, indent_sequences=False) -> bytes:
    dumper = IndentedDumper if indent_sequences else LiteralDumper
    return yaml.dump(value, Dumper=dumper, sort_keys=False, allow_unicode=True).encode("utf-8")


def anchored(value):
    if getattr(value, "merge", None) or getattr(getattr(value, "anchor", None), "value", None):
        return True
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return any(anchored(child) for child in children)


def update_mapping(target, proposed):
    """Patch only changed values; preserve comments, scalar styles and ordering."""
    if dict(target) == proposed:
        return
    if anchored(target):
        raise SpecError("Edits to YAML aliases, anchors, or merge mappings require manual review")
    for key in list(target):
        if key not in proposed:
            del target[key]
    for key, value in proposed.items():
        old = target.get(key)
        if old == value:
            continue
        if isinstance(old, dict) and isinstance(value, dict):
            update_mapping(old, value)
        elif key == "columns" and isinstance(old, list) and isinstance(value, list):
            existing = {c["name"]: c for c in old}
            ordered = []
            for column in value:
                item = existing.get(column["name"], {})
                update_mapping(item, column)
                ordered.append(item)
            old[:] = ordered
        else:
            if getattr(getattr(old, "anchor", None), "value", None):
                raise SpecError("Edits to YAML anchored values require manual review")
            target[key] = value
