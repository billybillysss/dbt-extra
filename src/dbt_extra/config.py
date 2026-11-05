"""Optional tool settings, project resolution, and explicit option overrides."""

import os
from pathlib import Path

from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import fields, mapping


def resolve_project(project_dir=None):
    value = project_dir if project_dir is not None else os.environ.get("EXTRA_PROJECT_DIR")
    if value is not None:
        return Path(value).absolute() / "extra_project.yaml"
    for directory in (Path.cwd(), *Path.cwd().parents):
        candidate = directory / "extra_project.yaml"
        if candidate.is_file():
            return candidate
    return Path.cwd() / "extra_project.yaml"


def strings(value, context):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
        raise SpecError(f"{context}: expected a list of nonempty strings")
    return value


def validate_settings(settings):
    allowed = {
        "dbt": {"project_dir", "artifacts"}, "analysis": {"dialect"},
        "inspection": {"expand", "optimize", "compile", "boundaries"},
        "export": {"output_dir", "default_view", "format", "select", "exclude", "views", "expand"},
        "optimization": {"format", "select", "exclude", "preserve_macros", "enrich"},
        "metadata": {"select", "exclude"},
    }
    fields(settings, {"version", *allowed}, set(), "extra_project.yaml")
    if settings.get("version", 2) != 2:
        raise SpecError("extra_project.yaml must use version: 2 tool configuration; models are dbt files")
    for key, keys in allowed.items():
        fields(mapping(settings.get(key, {}), key), keys, set(), key)
    for section, options in settings.items():
        if not isinstance(options, dict):
            continue
        for key, value in options.items():
            if key in {"select", "exclude", "boundaries"}:
                strings(value, f"{section}.{key}")
            if key in {"expand", "optimize", "compile", "preserve_macros", "enrich"} and type(value) is not bool:
                raise SpecError(f"{section}.{key}: expected a boolean")
            if key in {"output_dir", "default_view", "format", "dialect", "project_dir"} and (not isinstance(value, str) or not value):
                raise SpecError(f"{section}.{key}: expected nonempty text")
    views = mapping(settings.get("export", {}).get("views", {}), "export.views")
    for name, view in views.items():
        fields(mapping(view, f"export.views.{name}"), {"format", "select", "exclude", "expand"}, set(), f"export.views.{name}")
        if "expand" in view and type(view["expand"]) is not bool:
            raise SpecError(f"export.views.{name}.expand: expected a boolean")
        for key in {"select", "exclude"} & view.keys():
            strings(view[key], f"export.views.{name}.{key}")


def options(settings, section, overrides=None, *, view=None):
    result = dict(settings.get(section, {}))
    views = result.pop("views", {})
    if section == "export":
        selected = view or result.get("default_view")
        if selected:
            if selected not in views:
                raise SpecError(f"Unknown export view: {selected}")
            setting = mapping(views[selected], f"export.views.{selected}")
            fields(setting, {"format", "select", "exclude", "expand"}, set(), f"export.views.{selected}")
            result.update(setting)
    result.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return result
