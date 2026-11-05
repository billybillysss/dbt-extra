"""Guard package identity, review contracts, and release workflow boundaries."""

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
from dbt_extra.files.yaml import load_yaml
from dbt_extra.review import export_review, import_review
from tests.helpers import put, snapshot


ROOT = Path(__file__).resolve().parents[1]


def test_distribution_namespace_and_single_console_entry_point():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["name"] == "dbt-extra"
    assert metadata["project"]["scripts"] == {"extra": "dbt_extra.cli:cli"}
    assert metadata["tool"]["hatch"]["version"]["path"] == "src/dbt_extra/__init__.py"
    installed = distribution("dbt-extra")
    assert installed.version == __version__
    assert [(p.name, p.value) for p in installed.entry_points if p.group == "console_scripts"] == [
        ("extra", "dbt_extra.cli:cli"),
    ]
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"extra, version {__version__}"


def test_environment_and_upward_config_discovery(native, monkeypatch):
    monkeypatch.setenv("EXTRA_PROJECT_DIR", str(native))
    put(native, "extra_project.yaml", "version: 2\nanalysis:\n  dialect: duckdb\n")
    result = CliRunner().invoke(cli, ["validate"])
    assert result.exit_code == 0, result.output
    assert Project().config_path == native / "extra_project.yaml"
    monkeypatch.delenv("EXTRA_PROJECT_DIR")
    nested = native / "models/slv"
    monkeypatch.chdir(nested)
    assert Project().config_path == native / "extra_project.yaml"


def test_init_previews_config_and_refuses_overwrite(native):
    before = snapshot(native)
    result = CliRunner().invoke(cli, ["--project-dir", str(native), "init", "--preview"])
    assert result.exit_code == 0, result.output
    assert "extra_project.yaml" in result.output
    assert snapshot(native) == before
    arguments = ["--project-dir", str(native), "--dialect", "duckdb", "init"]
    result = CliRunner().invoke(cli, arguments)
    assert result.exit_code == 0, result.output
    contents = (native / "extra_project.yaml").read_bytes()
    assert b"extra/review" in contents
    result = CliRunner().invoke(cli, arguments)
    assert result.exit_code != 0 and "Refusing to overwrite" in result.output
    assert (native / "extra_project.yaml").read_bytes() == contents


@pytest.mark.parametrize("incompatible", [
    {"format_version": 2},
    {"format_version": 0},
    {"project": "another_project"},
])
def test_review_version_and_incompatible_baseline_rejection(native, incompatible):
    project = Project(native, dialect="duckdb")
    document = catalog(project, project.select(["revenue"]))
    assert document["format_version"] == 1
    assert "format" not in document
    export_review(project, format="csv", select=["revenue"])
    review = native / "extra/review"
    baseline_path = review / "_baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert baseline["format_version"] == 1
    assert "format" not in baseline
    assert baseline["files"] and baseline["tables"]
    assert import_review(Project(native, dialect="duckdb"), review).changed() == {}
    baseline.update(incompatible)
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    before = snapshot(native)
    with pytest.raises(SpecError, match="re-export"):
        import_review(Project(native, dialect="duckdb"), review)
    assert snapshot(native) == before


def test_only_release_workflow_can_publish_packages():
    workflows = ROOT / ".github/workflows"
    if not workflows.is_dir():
        pytest.skip("GitHub configuration is intentionally excluded from the source archive")
    for path in workflows.glob("*.yml"):
        if path.name == "release.yml":
            continue
        content = path.read_text(encoding="utf-8")
        assert "uv publish" not in content
        assert "twine upload" not in content
        assert "pypa/gh-action-pypi-publish" not in content
        assert "id-token: write" not in content
    release = load_yaml(workflows / "release.yml")
    assert release["on"]["push"] == {"tags": ["v*"]}
    assert "workflow_dispatch" in release["on"]
    assert release["permissions"] == {"contents": "read"}
    assert release["jobs"]["validate"] == {"uses": "./.github/workflows/ci.yml"}
    publish = release["jobs"]["publish"]
    assert publish["needs"] == "validate"
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    commands = [step["run"] for step in publish["steps"] if "run" in step]
    assert commands[0] == "uv sync --locked"
    assert commands[-3:] == [
        "uv build --no-sources", "uvx twine check dist/*", "uv publish --trusted-publishing always",
    ]
    check = next(step for step in publish["steps"] if step.get("name") == "Verify release tag matches package version")
    assert check["if"] == "startsWith(github.ref, 'refs/tags/')"
    assert check["env"] == {"RELEASE_TAG": "${{ github.ref_name }}"}


@pytest.mark.parametrize("tag", [f"v{__version__}", "v999.0.0"])
def test_release_tag_matches_package_version(tag, monkeypatch):
    path = ROOT / ".github/workflows/release.yml"
    if not path.is_file():
        pytest.skip("GitHub configuration is intentionally excluded from the source archive")
    release = load_yaml(path)
    check = next(step for step in release["jobs"]["publish"]["steps"]
                 if step.get("name") == "Verify release tag matches package version")
    command, script = check["run"].split("\n", 1)
    assert command == "uv run python - <<'PY'"
    script, terminator = script.rsplit("\n", 2)[:2]
    assert terminator == "PY"
    monkeypatch.setenv("RELEASE_TAG", tag)
    if tag == f"v{__version__}":
        exec(compile(script, str(path), "exec"), {})
    else:
        with pytest.raises(SystemExit, match="must match package version"):
            exec(compile(script, str(path), "exec"), {})


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.local = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        for key in ("src", "srcset", "href"):
            value = attributes.get(key)
            if value and not value.startswith(("https://", "http://", "#")):
                self.local.append(value)
        if tag == "img":
            self.images.append(attributes)


def test_readme_local_assets_exist_and_images_have_alt_text():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    parser = References()
    parser.feed(readme)
    assert all((ROOT / path).is_file() for path in parser.local)
    assert parser.images
    assert all(image.get("alt", "").strip() for image in parser.images)
