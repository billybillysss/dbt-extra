"""Optional dbt manifest/catalog evidence; never a source-rewrite input."""

import json

from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import mapping


def load_artifact(path, *, required, contents=None):
    raw = path.read_bytes() if path.is_file() else None
    if contents is not None:
        contents[path] = raw
    if raw is None:
        if required:
            raise SpecError(f"Artifact not found: {path}")
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
        mapping(value, str(path))
        for section in ("metadata", "nodes", "sources"):
            mapping(value.get(section, {}), f"{path}: {section}")
        for uid, node in {**value.get("nodes", {}), **value.get("sources", {})}.items():
            mapping(node, f"{path}: {uid}")
            for section in ("columns", "config"):
                mapping(node.get(section, {}), f"{path}: {uid}.{section}")
        return value
    except (ValueError, UnicodeError) as exc:
        raise SpecError(f"Invalid artifact {path}: {exc}") from exc
