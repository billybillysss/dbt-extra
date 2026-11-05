"""Keep the dbt-only library's dependency direction explicit."""

import ast
from pathlib import Path

import dbt_extra
from dbt_extra import ChangeSet, Project, SpecError
from dbt_extra.files.changes import ChangeSet as FileChangeSet
from dbt_extra.project import Project as DbtProject


ROOT = Path(dbt_extra.__file__).parent
RETIRED = {"dbt_extra.native", "dbt_extra.compiler", "dbt_extra.definitions", "dbt_extra.catalog", "dbt_extra.schema", "dbt_extra._legacy_cli"}


def imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_public_entry_points_are_shared_dbt_implementations():
    assert Project is DbtProject
    assert ChangeSet is FileChangeSet
    assert issubclass(SpecError, ValueError)


def test_no_retired_implementation_or_imports():
    for name in RETIRED:
        relative = name.removeprefix("dbt_extra.").replace(".", "/")
        assert not (ROOT / f"{relative}.py").exists()
        assert not list((ROOT / relative).rglob("*.py"))
    for path in ROOT.rglob("*.py"):
        assert not any(module == old or module.startswith(old + ".") for module in imports(path) for old in RETIRED), path


def test_core_packages_do_not_depend_on_review_or_cli():
    for package in ("project", "sql", "analysis"):
        for path in (ROOT / package).rglob("*.py"):
            assert not any(module == "dbt_extra.cli" or module.startswith("dbt_extra.review") for module in imports(path)), path
