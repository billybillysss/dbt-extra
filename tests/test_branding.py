"""Guard the new identity and private-preview release boundaries."""

from html.parser import HTMLParser
from importlib.metadata import distribution
import json
from pathlib import Path
import tomllib

from click.testing import CliRunner
import pytest

from dbt_extra import Project, SpecError, __version__
from dbt_extra.analysis import catalog
from dbt_extra.cli import cli
from dbt_extra.review import export_review, import_review
from tests.helpers import put, snapshot


ROOT = Path(__file__).resolve().parents[1]


def test_distribution_namespace_and_single_console_entry_point():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["name"] == "dbt-extra"
    assert metadata["project"]["scripts"] == {"extra": "dbt_extra.cli:cli"}
    assert metadata["tool"]["hatch"]["version"]["path"] == "src/dbt_extra/__init__.py"
    installed = distribution("dbt-extra")
    assert installed.version == __version__ == "0.1.0"
    assert [(p.name, p.value) for p in installed.entry_points if p.group == "console_scripts"] == [
        ("extra", "dbt_extra.cli:cli"),
    ]
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"extra, version {__version__}"


def test_new_environment_and_upward_config_discovery(native, monkeypatch):
    monkeypatch.setenv("EXTRA_PROJECT_DIR", str(native))
    put(native, "extra_project.yaml", "version: 2\nanalysis:\n  dialect: duckdb\n")
    result = CliRunner().invoke(cli, ["validate"])
    assert result.exit_code == 0, result.output
    assert Project().config_path == native / "extra_project.yaml"
    monkeypatch.delenv("EXTRA_PROJECT_DIR")
    nested = native / "models/slv"
    monkeypatch.chdir(nested)
    assert Project().config_path == native / "extra_project.yaml"


def test_legacy_environment_and_config_are_not_aliases(native, monkeypatch):
    monkeypatch.delenv("EXTRA_PROJECT_DIR", raising=False)
    monkeypatch.setenv("slbt_PROJECT_DIR", str(native / "missing"))
    monkeypatch.setenv("SLBT_PROJECT_DIR", str(native / "missing"))
    put(native, "slbt_project.yaml", "version: 1\nmodels: obsolete\n")
    monkeypatch.chdir(native)
    project = Project(dialect="duckdb")
    assert project.root == native
    assert project.config_path == native / "extra_project.yaml"
    assert project.settings == {}


def test_init_previews_new_config_only_and_refuses_overwrite(native):
    before = snapshot(native)
    result = CliRunner().invoke(cli, ["--project-dir", str(native), "init", "--preview"])
    assert result.exit_code == 0, result.output
    assert "extra_project.yaml" in result.output
    assert snapshot(native) == before
    arguments = ["--project-dir", str(native), "--dialect", "duckdb", "init"]
    result = CliRunner().invoke(cli, arguments)
    assert result.exit_code == 0, result.output
    contents = (native / "extra_project.yaml").read_bytes()
    assert b"extra_review" in contents
    result = CliRunner().invoke(cli, arguments)
    assert result.exit_code != 0 and "Refusing to overwrite" in result.output
    assert (native / "extra_project.yaml").read_bytes() == contents


def test_new_review_envelope_and_legacy_baseline_rejection(native):
    project = Project(native, dialect="duckdb")
    document = catalog(project, project.select(["revenue"]))
    assert (document["format"], document["format_version"]) == ("dbt-extra.dbt-review", 2)
    export_review(project, format="csv", select=["revenue"])
    review = native / "extra_review"
    baseline_path = review / "_baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert baseline["format"] == "dbt-extra.dbt-review-baseline"
    assert import_review(Project(native, dialect="duckdb"), review).changed() == {}
    baseline["format"] = "slbt.dbt-review-baseline"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    before = snapshot(native)
    with pytest.raises(SpecError):
        import_review(Project(native, dialect="duckdb"), review)
    assert snapshot(native) == before


def test_runtime_contains_no_old_namespace_or_command():
    package = ROOT / "src/dbt_extra"
    if not package.is_dir():
        pytest.skip("Source paths are absent in installed-wheel-only environments")
    for path in package.rglob("*.py"):
        assert "slbt" not in path.read_text(encoding="utf-8").lower(), path


def test_workflows_cannot_publish_packages():
    workflows = ROOT / ".github/workflows"
    if not workflows.is_dir():
        pytest.skip("GitHub configuration is intentionally excluded from the source archive")
    for path in workflows.glob("*.yml"):
        content = path.read_text(encoding="utf-8")
        assert "uv publish" not in content
        assert "twine upload" not in content
        assert "pypa/gh-action-pypi-publish" not in content
        assert "id-token: write" not in content
    candidate = (workflows / "release.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in candidate and "tags:" not in candidate


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.local = []
        self.badges = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        for key in ("src", "srcset", "href"):
            value = attributes.get(key)
            if value and not value.startswith(("https://", "http://", "#")):
                self.local.append(value)
        if tag == "img" and attributes.get("src", "").startswith("https://"):
            self.badges.append(attributes)


def test_readme_uses_real_assets_and_no_unpublished_pypi_badge():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert '<h1 align="center">dbt-extra — dbt transformation review and inspection</h1>' in readme
    assert "https://github.com/billybillysss/dbt-extra.git" in readme
    assert "uv run --locked extra" in readme
    assert "img.shields.io/pypi/" not in readme
    parser = References()
    parser.feed(readme)
    assert all((ROOT / path).is_file() for path in parser.local)
    assert [badge["alt"] for badge in parser.badges] == [
        "License: MIT", "Python 3.11+", "CI", "Documentation",
    ]
