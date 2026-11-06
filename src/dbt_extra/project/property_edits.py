"""Prepare comment-preserving dbt YAML/config patches on checked file changes."""

import io

from ruamel.yaml import YAML

from dbt_extra.errors import SpecError
from dbt_extra.files.changes import digest
from dbt_extra.files.yaml import load_yaml, update_mapping
from dbt_extra.project.properties import scope_config, validate_properties


class PropertyEdits:
    def __init__(self, changes):
        self.changes = changes

    def _document(self, project, path):
        path = self.changes.watch(path, digest(project.contents[path]), check=True)
        load_yaml(path)  # strict duplicate-key and portable-literal checks
        parser = YAML(typ="rt")
        parser.preserve_quotes = True
        parser.width = 4096
        parser.indent(mapping=2, sequence=4, offset=2)
        # Always compose on staged bytes, including proposals from another editor.
        raw = self.changes.after.get(path, self.changes.before[path])
        return parser, parser.load(raw.decode("utf-8"))

    def project_config(self, project, locator, proposed):
        """Patch direct authored dbt config keys without replacing child scopes."""
        if (not locator or locator[0] not in {"models", "seeds", "snapshots"}
                or any(not isinstance(k, str) or k.startswith("+") for k in locator)):
            raise SpecError("Invalid dbt configuration scope")
        if any(not k.startswith("+") and isinstance(v, dict) for k, v in proposed.items()):
            raise SpecError("Mapping-valued dbt configuration requires a + prefix; child scopes cannot be edited as config")
        path = project.root / "dbt_project.yml"
        parser, document = self._document(project, path)
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
        self.changes.after[path] = stream.getvalue().encode("utf-8")

    def properties(self, project, resource, properties):
        validate_properties(properties, resource.id)
        if resource.path is None or resource.package != project.name:
            raise SpecError(f"Read-only package/artifact resource: {resource.id}")
        if resource.properties.get("versions") or properties.get("versions"):
            raise SpecError(f"Versioned properties are read-only: {resource.id}")
        path = resource.property_path
        if path is None:
            raise SpecError(f"No existing writable dbt YAML entry for {resource.id}; add one in dbt and retry")
        parser, document = self._document(project, path)
        target = document
        for key in resource.property_locator:
            target = target[key]
        if resource.kind == "source_group":
            properties = {**properties, "tables": target.get("tables", [])}
        update_mapping(target, properties)
        stream = io.StringIO()
        parser.dump(document, stream)
        self.changes.after[path] = stream.getvalue().encode("utf-8")
