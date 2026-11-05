"""One project root and explicit, stable path bases across Python and CLI."""

import json

from click.testing import CliRunner
import pytest

from dbt_extra.cli import cli
from dbt_extra.errors import SpecError
from dbt_extra.project import Project
from tests.helpers import put, snapshot


@pytest.fixture(autouse=True)
def no_project_environment(monkeypatch):
    monkeypatch.delenv("EXTRA_PROJECT_DIR", raising=False)


def test_nearest_dbt_root_wins_over_parent_and_child_settings(tmp_path, monkeypatch):
    put(tmp_path, "dbt_project.yml", "name: outer\n")
    put(tmp_path, "extra_project.yaml", "not: valid settings\n")
    root = tmp_path / "nested"
    put(root, "dbt_project.yml", "name: inner\n")
    put(root, "models/extra_project.yaml", "also: ignored\n")
    monkeypatch.chdir(root / "models")
    project = Project()
    assert project.root == root
    assert project.name == "inner"
    assert project.settings == {}
    assert project.config_path == root / "extra_project.yaml"
    put(root, "extra_project.yaml", "analysis: {dialect: duckdb}\n")
    assert Project().dialect == "duckdb"


def test_flag_overrides_environment_overrides_discovery(tmp_path, monkeypatch):
    for name in ("flag", "environment", "cwd"):
        put(tmp_path, f"{name}/dbt_project.yml", f"name: {name}\n")
    monkeypatch.chdir(tmp_path / "cwd")
    monkeypatch.setenv("EXTRA_PROJECT_DIR", "../environment")
    assert Project().name == "environment"
    assert Project("../flag").name == "flag"
    runner = CliRunner()
    environment = runner.invoke(cli, ["init", "--preview"])
    assert environment.exit_code == 0, environment.output
    assert str(tmp_path / "environment/extra_project.yaml") in environment.output
    flag = runner.invoke(cli, ["--project-dir", "../flag", "init", "--preview"])
    assert flag.exit_code == 0, flag.output
    assert str(tmp_path / "flag/extra_project.yaml") in flag.output
    assert not list(tmp_path.rglob("extra_project.yaml"))


@pytest.mark.parametrize("selection", ["argument", "environment"])
def test_explicit_directory_never_searches_parents(native, monkeypatch, selection):
    monkeypatch.chdir(native)
    directory = "models"
    if selection == "environment":
        monkeypatch.setenv("EXTRA_PROJECT_DIR", directory)
        directory = None
    with pytest.raises(SpecError, match="No dbt_project.yml"):
        Project(directory)
    result = CliRunner().invoke(cli, [*(["--project-dir", directory] if directory else []), "init", "--preview"])
    assert result.exit_code == 1, result.output
    assert "No dbt_project.yml" in result.output


@pytest.mark.parametrize("settings", [False, True])
def test_settings_alone_never_define_a_project(tmp_path, monkeypatch, settings):
    if settings:
        put(tmp_path, "extra_project.yaml", "version: 2\n")
    monkeypatch.chdir(tmp_path)
    before = snapshot(tmp_path)
    with pytest.raises(SpecError, match="No dbt_project.yml"):
        Project()
    result = CliRunner().invoke(cli, ["init"])
    assert result.exit_code == 1, result.output
    assert snapshot(tmp_path) == before


def test_init_discovers_root_from_subdirectory(native, monkeypatch):
    monkeypatch.chdir(native / "models/gld")
    runner = CliRunner()
    before = snapshot(native)
    preview = runner.invoke(cli, ["init", "--preview"])
    assert preview.exit_code == 0, preview.output
    assert str(native / "extra_project.yaml") in preview.output
    assert snapshot(native) == before
    applied = runner.invoke(cli, ["init"])
    assert applied.exit_code == 0, applied.output
    assert (native / "extra_project.yaml").is_file()
    refused = runner.invoke(cli, ["init"])
    assert refused.exit_code == 1
    assert "Refusing to overwrite" in refused.output


def test_cli_inputs_are_cwd_relative_but_outputs_are_project_relative(native, monkeypatch):
    cwd = native / "elsewhere"
    manifest = {"metadata": {"project_name": "shop", "adapter_type": "duckdb"}}
    put(cwd, "manifest.json", json.dumps(manifest))
    monkeypatch.chdir(cwd)
    runner = CliRunner()
    arguments = ["--project-dir", "..", "--manifest", "manifest.json"]
    exported = runner.invoke(cli, [*arguments, "export", "--format", "csv", "--output-dir", "review"])
    assert exported.exit_code == 0, exported.output
    assert (native / "review/_baseline.json").is_file()
    assert not (cwd / "review").exists()
    project = Project("..", manifest="manifest.json")
    assert project.manifest_path == cwd / "manifest.json"
    before = snapshot(native)
    imported = runner.invoke(cli, [*arguments, "import", "../review", "--preview"])
    assert imported.exit_code == 0, imported.output
    assert snapshot(native) == before
    missing = runner.invoke(cli, [*arguments, "import", "review", "--preview"])
    assert missing.exit_code == 2


def test_configured_artifacts_are_project_relative(native, monkeypatch):
    put(native, "evidence/manifest.json", json.dumps({"metadata": {"project_name": "shop", "adapter_type": "duckdb"}}))
    put(native, "extra_project.yaml", "dbt:\n  artifacts:\n    manifest: evidence/manifest.json\n")
    monkeypatch.chdir(native / "models/gld")
    project = Project()
    assert project.manifest_path == native / "evidence/manifest.json"
    assert project.dialect == "duckdb"
