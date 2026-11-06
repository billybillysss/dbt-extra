"""An operation-local snapshot of an existing dbt project."""

from __future__ import annotations

from pathlib import Path

from dbt_extra.config import options, resolve_project, strings, validate_settings
from dbt_extra.errors import SpecError
from dbt_extra.files.paths import safe_path, within
from dbt_extra.files.yaml import fields, load_yaml, mapping
from dbt_extra.project.artifacts import load_artifact
from dbt_extra.project.discovery import discover
from dbt_extra.project.selectors import select
from dbt_extra.sql.dialects import resolve_dialect


class Project:
    def __init__(self, directory=None, *, dialect=None, manifest=None):
        self.root = resolve_project(directory)
        self.config_path = self.root / "extra_project.yaml"
        safe_path(self.config_path)
        self.config_content = self.config_path.read_bytes() if self.config_path.is_file() else None
        self.settings = load_yaml(self.config_path, {self.config_path: self.config_content}) if self.config_content is not None else {}
        validate_settings(self.settings)
        dbt = self.settings.get("dbt", {})
        project_file = self.root / "dbt_project.yml"
        self.contents = {project_file: project_file.read_bytes(), self.config_path: self.config_content}
        self.authored = load_yaml(project_file, self.contents)
        self.name = self.authored.get("name")
        if not isinstance(self.name, str) or not self.name:
            raise SpecError("dbt_project.yml requires a project name")
        self.model_roots = self.roots("model-paths", ["models"])
        self.macro_roots = self.roots("macro-paths", ["macros"])
        self.snapshot_roots = self.roots("snapshot-paths", ["snapshots"])
        self.seed_roots = self.roots("seed-paths", ["seeds"])
        artifacts = mapping(dbt.get("artifacts", {}), "dbt.artifacts")
        fields(artifacts, {"manifest", "catalog"}, set(), "dbt.artifacts")
        self.manifest_path = Path(manifest).resolve() if manifest else (self.root / artifacts.get("manifest", "target/manifest.json")).resolve()
        self.manifest = load_artifact(self.manifest_path, required=bool(manifest or "manifest" in artifacts), contents=self.contents)
        artifact_project = self.manifest.get("metadata", {}).get("project_name")
        if artifact_project and artifact_project != self.name:
            raise SpecError(f"Manifest project {artifact_project!r} does not match dbt project {self.name!r}")
        self.catalog = load_artifact((self.root / artifacts["catalog"]).resolve(), required=True, contents=self.contents) if artifacts.get("catalog") else {}
        adapter = self.manifest.get("metadata", {}).get("adapter_type")
        self.dialect = resolve_dialect(dialect or self.settings.get("analysis", {}).get("dialect", "auto"), adapter=adapter)
        self.resources = {}
        self.diagnostics = []
        discover(self)
        for resource in self.resources.values():
            evidence = {**self.catalog.get("nodes", {}), **self.catalog.get("sources", {})}.get(resource.id, {})
            resource.catalog_columns = {col["name"]: {"name": col["name"], "data_type": col.get("type", "")}
                                        for col in evidence.get("columns", {}).values() if isinstance(col, dict) and col.get("name")}

    def roots(self, key, default):
        roots = [within(self.root, p) for p in strings(self.authored.get(key, default), key)]
        if len(set(roots)) != len(roots) or any(a != b and a.is_relative_to(b) for a in roots for b in roots):
            raise SpecError(f"{key}: roots must be distinct and non-overlapping")
        return roots

    def require_dialect(self):
        if not self.dialect:
            raise SpecError("SQL analysis requires --dialect, analysis.dialect, or a manifest adapter_type")
        return self.dialect

    def options(self, section, overrides=None, *, view=None):
        return options(self.settings, section, overrides, view=view)

    def select(self, selections=None, exclude=None, *, kinds=None):
        return select(self.resources.values(), selections, exclude, kinds=kinds)

    def find_model(self, name):
        if name in self.resources:
            resource = self.resources[name]
            if resource.kind != "model":
                raise SpecError(f"Inspection requires a model: {name}")
            return resource
        candidates = [r for r in self.resources.values() if r.name == name and r.kind == "model"]
        if len(candidates) != 1:
            raise SpecError(f"Unknown or ambiguous model {name}: {', '.join(r.id for r in candidates)}")
        return candidates[0]
