"""Comment-preserving property patches and checked, rollback-capable writes."""

from __future__ import annotations

import difflib
import hashlib
import io
import os
import tempfile
from pathlib import Path

from ruamel.yaml import YAML

from dbt_extra.files.paths import safe_path, within
from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import load_yaml, update_mapping
from dbt_extra.project.properties import scope_config, validate_properties


def digest(content):
    return hashlib.sha256(content).hexdigest() if content is not None else None


def content(path):
    return path.read_bytes() if path.is_file() else None


class ChangeSet:
    def __init__(self, root):
        root = Path(root).absolute()
        safe_path(root)
        self.root = root.resolve()
        self.before = {}
        self.after = {}
        self.documents = {}

    def watch(self, path, expected=None, *, check=False, external=False):
        # Only read-set checks may explicitly watch external tool settings.
        # set() always enforces the write root regardless of prior watches.
        path = Path(path).absolute() if external else within(self.root, str(path))
        safe_path(path)
        current = content(path)
        if check and digest(current) != expected:
            raise SpecError(f"Conflict: {path} changed since export; re-export before editing")
        self.before.setdefault(path, current)
        return path

    def set(self, path, value):
        path = self.watch(path)
        self.after[path] = value.encode("utf-8") if isinstance(value, str) else value

    def project_config(self, project, locator, proposed):
        """Patch direct authored dbt config keys without replacing child scopes."""
        if (not locator or locator[0] not in {"models", "seeds", "snapshots"}
                or any(not isinstance(k, str) or k.startswith("+") for k in locator)):
            raise SpecError("Invalid dbt configuration scope")
        if any(not k.startswith("+") and isinstance(v, dict) for k, v in proposed.items()):
            raise SpecError("Mapping-valued dbt configuration requires a + prefix; child scopes cannot be edited as config")
        path = project.root / "dbt_project.yml"
        self.watch(path, digest(project.contents[path]), check=True)
        if path not in self.documents:
            parser = YAML(typ="rt")
            parser.preserve_quotes = True
            parser.width = 4096
            parser.indent(mapping=2, sequence=4, offset=2)
            load_yaml(path)
            self.documents[path] = parser, parser.load(self.before[path].decode("utf-8"))
        parser, document = self.documents[path]
        target = document
        for key in locator:
            if getattr(target, "merge", None) or getattr(getattr(target, "anchor", None), "value", None):
                raise SpecError("Edits to YAML aliases, anchors, or merge mappings require manual review")
            if not isinstance(target, dict) or key not in target:
                raise SpecError("dbt configuration scope changed since export")
            target = target[key]
        if not isinstance(target, dict):
            raise SpecError("dbt configuration scope must be a mapping")
        if scope_config(target) == proposed:
            return
        children = {k: v for k, v in target.items() if not k.startswith("+") and isinstance(v, dict)}
        if proposed.keys() & children.keys():
            raise SpecError("Configuration cannot replace a child dbt scope")
        update_mapping(target, {**children, **proposed})
        stream = io.StringIO()
        parser.dump(document, stream)
        self.after[path] = stream.getvalue().encode("utf-8")

    def properties(self, project, resource, properties):
        validate_properties(properties, resource.id)
        if resource.path is None or resource.package != project.name:
            raise SpecError(f"Read-only package/artifact resource: {resource.id}")
        if resource.properties.get("versions") or properties.get("versions"):
            raise SpecError(f"Versioned properties are read-only: {resource.id}")
        path = resource.property_path
        if path is None:
            raise SpecError(f"No existing writable dbt YAML entry for {resource.id}; add one in dbt and retry")
        self.watch(path, digest(project.contents[path]), check=True)
        path = self.watch(path)
        if path not in self.documents:
            parser = YAML(typ="rt")
            parser.preserve_quotes = True
            parser.width = 4096
            parser.indent(mapping=2, sequence=4, offset=2)
            raw = self.before[path]
            load_yaml(path)  # strict duplicate-key and portable-literal checks
            document = parser.load(raw.decode("utf-8"))
            self.documents[path] = parser, document
        parser, document = self.documents[path]
        target = document
        for key in resource.property_locator:
            target = target[key]
        if resource.kind == "source_group":
            properties = {**properties, "tables": target.get("tables", [])}
        update_mapping(target, properties)
        stream = io.StringIO()
        parser.dump(document, stream)
        self.after[path] = stream.getvalue().encode("utf-8")

    def changed(self):
        return {p: data for p, data in self.after.items() if data != self.before[p]}

    def diffs(self):
        return "".join("".join(difflib.unified_diff(
            (self.before[p] or b"").decode("utf-8").splitlines(keepends=True),
            data.decode("utf-8").splitlines(keepends=True),
            fromfile=p.relative_to(self.root).as_posix(), tofile=p.relative_to(self.root).as_posix(),
        )) for p, data in self.changed().items())

    def apply(self, *, preview=False):
        changed = self.changed()
        # Check the whole read set, even when individual staged updates are no-ops.
        for path, before in self.before.items():
            safe_path(path)
            if content(path) != before:
                raise SpecError(f"Conflict: {path} changed while preparing edits")
        if preview:
            return list(changed)
        staged, written, created = {}, [], []
        try:
            for path, data in changed.items():
                missing = []
                parent = path.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                for parent in reversed(missing):
                    parent.mkdir()
                    created.append(parent)
                staged[path] = temporary(path, data)
            for path in changed:
                safe_path(path)
                if content(path) != self.before[path]:
                    raise SpecError(f"Conflict: {path} changed while staging edits")
            for path, stage in staged.items():
                os.replace(stage, path)
                written.append(path)
        except Exception:
            for path in reversed(written):
                original = self.before[path]
                if original is None:
                    path.unlink()
                else:
                    restore = temporary(path, original)
                    os.replace(restore, path)
            raise
        finally:
            for stage in staged.values():
                stage.unlink(missing_ok=True)
            for directory in reversed(created):
                if not any(directory.iterdir()):
                    directory.rmdir()
        return list(changed)


def temporary(path, data):
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".extra", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        if path.exists():
            os.chmod(name, path.stat().st_mode)
        return Path(name)
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise
