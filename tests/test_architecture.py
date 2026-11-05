"""Keep the dbt-only library's dependency direction explicit."""

import ast
from pathlib import Path

import dbt_extra
from dbt_extra import ChangeSet, Project, SpecError
from dbt_extra.files.changes import ChangeSet as FileChangeSet
from dbt_extra.project import Project as DbtProject


ROOT = Path(dbt_extra.__file__).parent


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


def test_core_packages_do_not_depend_on_review_or_cli():
    for package in ("project", "sql", "analysis"):
        for path in (ROOT / package).rglob("*.py"):
            assert not any(module == "dbt_extra.cli" or module.startswith("dbt_extra.review") for module in imports(path)), path
