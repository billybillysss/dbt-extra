"""Manifest aliases and explicit dialect precedence share one resolver."""

import json

from click.testing import CliRunner
import pytest

from dbt_extra.cli import cli
from dbt_extra.errors import SpecError
from dbt_extra.project import Project
from dbt_extra.sql.dialects import resolve_dialect
from dbt_extra.validation import validate
from tests.helpers import put


@pytest.mark.parametrize("adapter,dialect", [
    ("fabricspark", "spark"), ("fabric", "fabric"), ("sqlserver", "tsql"),
    ("spark", "spark"), ("tsql", "tsql"), ("databricks", "databricks"),
    ("postgres", "postgres"), ("duckdb", "duckdb"),
])
def test_manifest_adapter_resolution(native, adapter, dialect):
    put(native, "target/manifest.json", json.dumps({"metadata": {"adapter_type": adapter}}))
    assert Project(native).require_dialect() == dialect


@pytest.mark.parametrize("adapter", ["unknown_adapter", {}, 123])
def test_unknown_or_malformed_adapter_needs_an_explicit_choice(native, adapter):
    put(native, "target/manifest.json", json.dumps({"metadata": {"adapter_type": adapter}}))
    with pytest.raises(SpecError, match="set --dialect or analysis.dialect explicitly"):
        Project(native)
    assert Project(native, dialect="fabric").require_dialect() == "fabric"


@pytest.mark.parametrize("configured,explicit,expected", [
    ("fabric", None, "fabric"), ("fabric", "duckdb", "duckdb"),
    ("auto", None, "spark"), ("fabric", "auto", "spark"),
])
def test_explicit_then_configured_then_manifest_precedence(native, configured, explicit, expected):
    put(native, "target/manifest.json", json.dumps({"metadata": {"adapter_type": "fabricspark"}}))
    put(native, "extra_project.yaml", f"version: 2\nanalysis:\n  dialect: {configured}\n")
    assert Project(native, dialect=explicit).require_dialect() == expected


def test_missing_adapter_keeps_metadata_and_template_validation_available(native):
    assert resolve_dialect() is None
    project = Project(native)
    assert project.dialect is None
    assert set(validate(project).values()) == {"No SQL dialect available"}
    with pytest.raises(SpecError, match="requires --dialect"):
        project.require_dialect()


@pytest.mark.parametrize("arguments,expected", [
    (["--dialect", "tsql", "export", "--dialect", "fabric"], "fabric"),
    (["--dialect", "tsql", "export"], "tsql"),
    (["export"], "spark"),
])
def test_cli_command_then_global_then_configuration_precedence(native, arguments, expected):
    put(native, "extra_project.yaml", "version: 2\nanalysis:\n  dialect: spark\n")
    response = CliRunner().invoke(cli, ["--project-dir", str(native), *arguments,
                                       "--format", "json", "--output-dir", "review"])
    assert response.exit_code == 0, response.output
    assert json.loads((native / "review/review.json").read_text())["dialect"] == expected


def test_invalid_dialect_is_a_friendly_cli_error(native):
    response = CliRunner().invoke(cli, ["--project-dir", str(native), "--dialect", "not_a_dialect", "validate"])
    assert response.exit_code == 1
    assert "Invalid SQL dialect" in response.output
    assert "SQLGlot dialect name" in response.output
