"""Keep the dbt-only library's dependency direction explicit."""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import dbt_extra
import pytest
from dbt_extra import ChangeSet, Project, SpecError
from dbt_extra.files.changes import ChangeSet as FileChangeSet
from dbt_extra.project import Project as DbtProject


ROOT = Path(dbt_extra.__file__).parent


def imports(path):
    relative = path.relative_to(ROOT.parent).with_suffix("")
    package = ".".join(relative.parts[:-1])
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = importlib.util.resolve_name("." * node.level + module, package)
            yield module
            yield from (f"{module}.{alias.name}" for alias in node.names)


def test_public_entry_points_are_shared_dbt_implementations():
    assert Project is DbtProject
    assert ChangeSet is FileChangeSet
    assert issubclass(SpecError, ValueError)


def test_core_packages_do_not_depend_on_review_or_cli():
    for package in ("project", "sql", "analysis"):
        for path in (ROOT / package).rglob("*.py"):
            assert not any(module == "dbt_extra.cli" or module.startswith("dbt_extra.review") for module in imports(path)), path


@pytest.mark.parametrize("package, forbidden", [
    ("sql", ("project", "analysis", "review", "cli", "inspection", "optimization", "enrichment", "validation", "workflow_results")),
    ("files", ("project", "sql", "analysis", "review", "cli", "workflow_results")),
])
def test_low_level_packages_are_project_and_workflow_independent(package, forbidden):
    prefixes = tuple(f"dbt_extra.{name}" for name in forbidden)
    for path in (ROOT / package).rglob("*.py"):
        for module in imports(path):
            assert not any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes), (path, module)


@pytest.mark.parametrize("name", ["syntax", "interpreter", "expansion"])
def test_template_interpretation_does_not_depend_on_sql_parsing(name):
    assert "dbt_extra.sql.parser" not in imports(ROOT / "sql/templates" / f"{name}.py")


def test_function_catalogs_depend_only_on_records():
    for path in (ROOT / "sql/functions").glob("*.py"):
        if path.stem in {"__init__", "models", "registry"}:
            continue
        internal = {module for module in imports(path) if module.startswith("dbt_extra")}
        assert internal == {
            "dbt_extra.sql.functions.models", "dbt_extra.sql.functions.models.FunctionSpec",
        }, path
    assert not any(module.startswith("dbt_extra.sql.functions")
                   for module in imports(ROOT / "sql/functions/models.py"))


def test_sql_module_dependencies_are_acyclic():
    paths = list((ROOT / "sql").rglob("*.py"))
    modules = {".".join(path.relative_to(ROOT.parent).with_suffix("").parts).removesuffix(".__init__"): path
               for path in paths}
    active, complete = set(), set()

    def visit(module):
        assert module not in active, f"SQL dependency cycle at {module}"
        if module in complete:
            return
        active.add(module)
        for dependency in imports(modules[module]):
            if dependency in modules:
                visit(dependency)
        active.remove(module)
        complete.add(module)

    for module in modules:
        visit(module)


@pytest.mark.parametrize("module", [
    "dbt_extra.sql.templates.macros", "dbt_extra.sql.templates.expansion",
    "dbt_extra.sql.functions.registry", "dbt_extra.sql.rewrites.engine",
])
def test_sql_imports_work_in_fresh_processes_without_loading_projects(module):
    result = subprocess.run([sys.executable, "-c", f"""
import importlib
import sys
importlib.import_module({module!r})
from dbt_extra.sql.rewrites.engine import optimize_source
assert '3 AS k' in optimize_source('SELECT 1+2 AS k', 'duckdb')
assert not any(name.startswith(('dbt_extra.project', 'dbt_extra.review', 'dbt_extra.analysis')) for name in sys.modules)
"""], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module", [
    "sql.inspection_cleanup", "sql.inspection_rules", "sql.transactions", "sql.partial",
    "sql.source_rules", "sql.source_expressions", "sql.projections", "sql.macros",
    "sql.static_jinja", "sql.jinja", "sql.config_format", "sql.shorthand",
    "sql.schema_evidence", "sql.references", "sql.relations",
    "analysis.models", "analysis.types", "review.workbook",
])
def test_removed_module_paths_have_no_compatibility_shims(module):
    assert importlib.util.find_spec(f"dbt_extra.{module}") is None
