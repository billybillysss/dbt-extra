"""Offline documentation contracts: real examples and resolvable local links."""

import json
from pathlib import Path
import re
import shlex
import shutil
from urllib.parse import unquote, urlsplit

from click.testing import CliRunner
from openpyxl import load_workbook
import pytest

from dbt_extra import __version__
from dbt_extra.cli import cli
from dbt_extra.analysis import catalog
from dbt_extra.project import Project
from dbt_extra.files.yaml import load_yaml
from dbt_extra.sql.parser import parse_authored
from tests.helpers import optimizer_inputs, snapshot


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/jaffle_shop"
DOCUMENTS = sorted({
    *ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"),
    *(ROOT / "examples").rglob("README.md"),
    *(ROOT / ".github").rglob("*.md"),
})


@pytest.fixture
def dbt_example(tmp_path):
    destination = tmp_path / "examples/jaffle_shop"
    shutil.copytree(EXAMPLE, destination, ignore=shutil.ignore_patterns("target", "logs", "extra", "dbt_packages"))
    return destination


def blocks(text, language):
    return re.findall(rf"^```{language}\n(.*?)^```", text, re.MULTILINE | re.DOTALL)


def prose(text):
    return re.sub(r"^```[^\n]*\n.*?^```[^\n]*$", "", text, flags=re.MULTILINE | re.DOTALL)


def anchors(text):
    """GitHub-style heading slugs for the headings used in these docs."""
    result, counts = set(), {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", prose(text), re.MULTILINE):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        result.add(f"{slug}-{count}" if count else slug)
    return result


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_local_markdown_links(path):
    for href in re.findall(r"\[[^\]\n]+\]\(([^)\s]+)\)", prose(path.read_text(encoding="utf-8"))):
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc:
            continue
        target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
        assert target.is_relative_to(ROOT), f"{path}: link leaves repository: {href}"
        assert target.exists(), f"{path}: missing local link: {href}"
        if parsed.fragment and target.suffix == ".md":
            assert unquote(parsed.fragment) in anchors(target.read_text(encoding="utf-8")), f"{path}: missing anchor: {href}"


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_json_examples_parse(path):
    for block in blocks(path.read_text(encoding="utf-8"), "json"):
        json.loads(block)


def test_readme_config_and_native_example(tmp_path):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    example = tmp_path / "readme.yml"
    example.write_text(blocks(readme, "yaml")[0], encoding="utf-8")
    settings = load_yaml(example)
    assert settings["version"] == 2
    assert settings["analysis"] == load_yaml(EXAMPLE / "extra_project.yaml")["analysis"]
    project = Project(EXAMPLE)
    document = catalog(project, project.select(settings["export"]["select"]))
    assert document["source_of_truth"] == "dbt"
    names = {r["name"] for r in document["resources"]}
    assert {"customer_revenue", "macro_revenue", "gld_orders", "gld_customer_leaderboard"} <= names
    assert next(r for r in document["resources"] if r["name"] == "customer_revenue")["model_path"] == "models/gld"


def test_readme_inspection_example_matches_cli():
    result = CliRunner().invoke(cli, ["--project-dir", str(EXAMPLE), "inspect", "customer_revenue", "--columns", "revenue"])
    assert result.exit_code == 0, result.output
    query = "\n".join(line for line in result.output.splitlines() if not line.startswith("--"))
    assert 'AS "revenue"' in query
    assert "{{ ref('demo_raw_orders') }}" in query
    assert "completed" in query


def test_readme_shown_sql_matches_cli(dbt_example):
    before = snapshot(dbt_example)
    result = CliRunner().invoke(cli, ["--project-dir", str(dbt_example), "inspect",
        "customer_revenue", "--columns", "revenue", "--compile", "false"])
    assert result.exit_code == 0, result.output
    query = "\n".join(line for line in result.output.splitlines() if not line.startswith("--"))
    section = (ROOT / "README.md").read_text(encoding="utf-8").split("## See where a column comes from\n", 1)[1].split("\n## ", 1)[0]
    shown = blocks(section, "sql")
    assert len(shown) == 1
    assert shown[0].strip() == query.strip()
    assert snapshot(dbt_example) == before


def test_readme_selected_column_simplification_matches_cli(dbt_example, monkeypatch):
    monkeypatch.delenv("EXTRA_PROJECT_DIR", raising=False)
    monkeypatch.chdir(dbt_example)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("### Simplify the logic for one selected column\n", 1)[1].split("\n## ", 1)[0]
    commands, shown = blocks(section, "bash"), blocks(section, "sql")
    assert len(commands) == len(shown) == 2
    before = snapshot(dbt_example)
    for command, expected in zip(commands, shown):
        executable, *arguments = shlex.split(command)
        assert executable == "extra"
        result = CliRunner().invoke(cli, arguments)
        assert result.exit_code == 0, result.output
        query = "\n".join(line for line in result.output.splitlines() if not line.startswith("--"))
        assert query.strip() == expected.strip()
        assert snapshot(dbt_example) == before
    assert "COUNT(*) AS order_count" in shown[0]
    assert "order_count" not in shown[1]
    assert 'SUM("extra_input_1".amount)' in shown[1]
    assert 'GROUP BY\n      "extra_input_1".customer_id' in shown[1]
    assert "order_totals.revenue + 0 AS revenue" in shown[1]


def test_readme_enrichment_yaml_matches_real_proposal(dbt_example, tmp_path):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Fill missing metadata with real YAML\n", 1)[1].split("\n## ", 1)[0]
    examples = blocks(section, "yaml")
    assert len(examples) == 2
    shown = []
    for index, block in enumerate(examples):
        path = tmp_path / f"enrichment-{index}.yml"
        path.write_text(block, encoding="utf-8")
        document = load_yaml(path)
        assert document["version"] == 2
        assert len(document["models"]) == 1
        shown.append(document["models"][0])

    def revenue_properties():
        return next(model for model in load_yaml(dbt_example / "models/schema.yml")["models"]
                    if model["name"] == "customer_revenue")

    assert shown[0] == revenue_properties()
    before = snapshot(dbt_example)
    runner = CliRunner()
    arguments = ["--project-dir", str(dbt_example), "enrich", "--select", "customer_revenue"]
    preview = runner.invoke(cli, [*arguments, "--preview"])
    assert preview.exit_code == 0, preview.output
    assert "4 missing properties inferred; 2 unresolved" in preview.output
    assert snapshot(dbt_example) == before
    applied = runner.invoke(cli, arguments)
    assert applied.exit_code == 0, applied.output
    assert shown[1] == revenue_properties()
    after = snapshot(dbt_example)
    assert {path for path in before if before[path] != after[path]} == {"models/schema.yml"}


def test_readme_settings_support_named_view_and_workflow_defaults(dbt_example):
    settings = blocks((ROOT / "README.md").read_text(encoding="utf-8"), "yaml")[0]
    (dbt_example / "extra_project.yaml").write_text(settings, encoding="utf-8")
    project = Project(dbt_example)
    assert project.options("inspection", {})["compile"] is True
    assert project.options("metadata", {})["select"] == ["customer_revenue"]
    assert project.options("optimization", {})["expand"] is False
    before = snapshot(dbt_example)
    result = CliRunner().invoke(cli, ["--project-dir", str(dbt_example), "export", "--view", "finance", "--preview"])
    assert result.exit_code == 0, result.output
    assert "review.xlsx" in result.output
    assert snapshot(dbt_example) == before


def test_readme_json_example_includes_explicit_upstream_context(dbt_example):
    result = CliRunner().invoke(cli, ["--project-dir", str(dbt_example), "export", "--format", "json",
        "--select", "customer_revenue", "orders", "demo_raw_orders", "--output-dir", "extra/review-json"])
    assert result.exit_code == 0, result.output
    document = json.loads((dbt_example / "extra/review-json/review.json").read_text(encoding="utf-8"))
    assert document["format_version"] == 1
    assert document["source_of_truth"] == "dbt"
    assert {resource["name"] for resource in document["resources"]} == {
        "customer_revenue", "orders", "demo_raw_orders",
    }


def test_documented_description_review_round_trip(dbt_example):
    """Follow the Excel guide on a disposable project, never the teaching inputs."""
    runner = CliRunner()
    arguments = ["--project-dir", str(dbt_example)]
    original = snapshot(dbt_example)
    result = runner.invoke(cli, [*arguments, "export", "--format", "xlsx", "--select", "customer_revenue"])
    assert result.exit_code == 0, result.output
    workbook = dbt_example / "extra/review/review.xlsx"
    guide = (ROOT / "docs/guides/catalog-round-trip.md").read_text(encoding="utf-8")
    description = blocks(guide, "text")[0].strip()
    book = load_workbook(workbook)
    edited = 0
    try:
        for sheet in book:
            headers = [cell.value for cell in sheet[1]]
            if not {"Type", "Path", "Name", "Description"} <= set(headers):
                continue
            for row in sheet.iter_rows(min_row=2):
                if (row[headers.index("Type")].value == "TABLE"
                        and row[headers.index("Name")].value == "customer_revenue"):
                    assert row[headers.index("Path")].value == "models/gld"
                    cell = row[headers.index("Description")]
                    assert not cell.protection.locked
                    cell.value = description
                    edited += 1
        assert edited == 1
        book.save(workbook)
    finally:
        book.close()
    before_preview = snapshot(dbt_example)
    preview = runner.invoke(cli, [*arguments, "import", str(workbook), "--preview"])
    assert preview.exit_code == 0, preview.output
    assert "models/schema.yml" in preview.output.replace("\\", "/")
    assert description in preview.output
    assert snapshot(dbt_example) == before_preview
    applied = runner.invoke(cli, [*arguments, "import", str(workbook)])
    assert applied.exit_code == 0, applied.output
    after = snapshot(dbt_example)
    assert {path for path, content in original.items() if after[path] != content} == {"models/schema.yml"}
    models = load_yaml(dbt_example / "models/schema.yml")["models"]
    assert next(model for model in models if model["name"] == "customer_revenue")["description"] == description


@pytest.mark.parametrize("name", ["bug_report", "feature_request"])
@pytest.mark.skipif(not (ROOT / ".github").is_dir(), reason="GitHub metadata is not shipped in source distributions")
def test_github_issue_forms_have_valid_required_inputs(name):
    form = load_yaml(ROOT / f".github/ISSUE_TEMPLATE/{name}.yml")
    assert form["name"] and form["description"]
    inputs = [field for field in form["body"] if field["type"] != "markdown"]
    identities = [field["id"] for field in inputs]
    assert len(identities) == len(set(identities))
    assert all(field["type"] == "textarea" and field["attributes"]["label"] for field in inputs)
    assert any(field.get("validations", {}).get("required") is True for field in inputs)


def test_readme_python_api_is_read_only(monkeypatch, dbt_example, tmp_path):
    monkeypatch.delenv("EXTRA_PROJECT_DIR", raising=False)
    monkeypatch.chdir(dbt_example)
    before = snapshot(dbt_example)
    namespace = {}
    exec(blocks((ROOT / "README.md").read_text(encoding="utf-8"), "python")[0], namespace)
    assert namespace["document"]["resources"][0]["name"] == "customer_revenue"
    assert not namespace["skipped"]
    assert snapshot(dbt_example) == before


def test_readme_optimization_rewrites_only_authored_sql(dbt_example):
    destination = dbt_example
    path = destination / "models/gld/customer_revenue.sql"
    # The working example may already have been optimized; seed this isolated copy.
    path.write_text("""{{ config(materialized='table', tags=['finance']) }}
with order_totals as (
    select customer_id, sum(amount) as revenue, count(*) as order_count
    from {{ ref('orders') }} group by customer_id
)
select customer_id, revenue + 0 as revenue, order_count from order_totals
""", encoding="utf-8")
    original = path.read_text(encoding="utf-8")
    arguments = ["--project-dir", str(destination), "optimize", "-s", "customer_revenue"]
    before = {path: path.read_bytes() for path in destination.rglob("*") if path.is_file()}
    preview = CliRunner().invoke(cli, [*arguments, "--preview"])
    assert preview.exit_code == 0, preview.output
    assert {path: path.read_bytes() for path in destination.rglob("*") if path.is_file()} == before
    result = CliRunner().invoke(cli, arguments)
    assert result.exit_code == 0, result.output
    updated = path.read_text(encoding="utf-8")
    assert updated != original
    assert "{{ ref('orders') }}" in updated
    assert parse_authored(original, "duckdb").config == parse_authored(updated, "duckdb").config
    assert updated.startswith("{{ config(\n    materialized='table',\n    tags=[\n        'finance'\n    ]\n) }}")
    assert {p for p in before if p.read_bytes() != before[p]} == {path}


def test_optimization_fixtures_remain_teaching_inputs(dbt_example):
    optimizer_inputs(dbt_example)
    folder = dbt_example / "models/gld/optimization"
    inputs = {
        "gld_optimizer_constants": ["100 / 100 AS currency_scale", "1 + 2 AS sample_value"],
        "gld_customer_lifetime_value": ["WITH projected_orders AS (", "normalized_orders AS (",
                                        "o.status AS unused_status", "p.amount + 0 AS amount"],
        "gld_customer_leaderboard": ["SELECT DISTINCT", "MAX(c.amount) AS largest_order",
                                     "AS returned_order_count", "WITH scored AS (", "HAVING", "LIMIT 2"],
        "gld_customer_order_ranking": ["ROW_NUMBER() OVER", "r.position <= 2",
                                       "r.customer_id", "LIMIT 10"],
        "gld_distinct_paying_customers": ["SELECT DISTINCT", "o.order_id"],
        "gld_high_value_customers": ["AVG(benchmark_order.amount)", "AND EXISTS("],
        "gld_payment_union": ["UNION ALL"],
        "gld_optimizer_projections": ["o.status AS unused_status", "normalized AS (", "unused AS (", "AND TRUE"],
        "gld_optimizer_predicates": ["SELECT DISTINCT", "WHERE eligible.customer_id > 10 AND TRUE"],
        "gld_optimizer_schema_projection": ["SELECT *", "{{ ref('slv_orders') }}"],
        "gld_optimizer_boolean_normalization": ["(o.customer_id = 1 AND o.status = 'completed') OR"],
        "gld_optimizer_join_simplification": ["CROSS JOIN", "AND b.customer_id = c.customer_id"],
        "gld_optimizer_shared_subqueries": ["COUNT(*) AS order_count", "AS b ON a.customer_id = b.customer_id"],
        "gld_optimizer_customer_profile": ["c.first_name", "c.customer_lifetime_value", "{{ ref('gld_customers') }}"],
    }
    assert {path.stem for path in folder.glob("*.sql")} == set(inputs)
    for name, fragments in inputs.items():
        code = (folder / f"{name}.sql").read_text(encoding="utf-8")
        # Formatting and DuckDB's redundant NULLS LAST rendering are not rules.
        code = re.sub(r"\s+", " ", code)
        code = re.sub(r"\(\s+", "(", code)
        code = re.sub(r"\s+\)", ")", code)
        for fragment in fragments:
            assert fragment in code, f"{name}: missing teaching input {fragment!r}"

    before = snapshot(dbt_example)
    arguments = ["--project-dir", str(dbt_example), "optimize", "-s", "path:models/gld/optimization/**"]
    preview = CliRunner().invoke(cli, [*arguments, "--preview"])
    assert preview.exit_code == 0, preview.output
    assert "gld_optimizer_constants.sql" in preview.output
    assert snapshot(dbt_example) == before

    result = CliRunner().invoke(cli, arguments)
    assert result.exit_code == 0, result.output
    constants = (folder / "gld_optimizer_constants.sql").read_text(encoding="utf-8")
    assert "1 + 2" not in constants
    assert "3 AS sample_value" in constants


def test_cli_version_needs_no_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == f"extra, version {__version__}"


@pytest.mark.parametrize("arguments", [
    ["validate"],
    ["inspect", "customer_revenue", "--columns", "revenue"],
    ["inspect", "customer_revenue", "--columns", "revenue", "--from", "orders"],
    ["inspect", "customer_revenue", "--columns", "revenue", "--from", "orders", "--compile", "false"],
    ["inspect", "customer_revenue", "--columns", "revenue", "--view", "plan", "--compile", "false"],
    ["inspect", "customer_revenue", "--columns", "order_count", "--view", "plan"],
    ["inspect", "customer_revenue"],
    ["inspect", "customer_revenue", "--columns", "customer_id", "revenue", "--from", "orders", "--compile", "false"],
    ["inspect", "customer_revenue", "--expand", "false", "--optimize", "false", "--compile", "false"],
    ["export", "--format", "xlsx", "--preview"],
    ["export", "--format", "csv", "--preview"],
    ["export", "--format", "json", "--preview"],
    ["export", "--format", "xlsx", "--select", "macro_revenue", "--expand", "--output-dir", "extra/review-expanded", "--preview"],
    ["export", "--select", "orders", "customer_revenue", "--preview"],
    ["export", "--select", "path:models/gld/**", "--exclude", "macro_revenue", "--preview"],
    ["export", "--select", "tag:finance", "--preview"],
    ["export", "--view", "finance", "--preview"],
    ["optimize", "-s", "customer_revenue", "--preview"],
    ["optimize", "--select", "macro_revenue", "--expand", "true", "--preview"],
    ["optimize", "--select", "gld_optimizer_constants", "--preview"],
    ["optimize", "--select", "customer_revenue", "--format", "compact", "--enrich", "true", "--preview"],
    ["optimize", "--select", "model.jaffle_shop.customer_revenue", "--preview"],
    ["enrich", "-s", "customer_revenue", "--preview"],
])
def test_documented_preview_commands_succeed_without_writes(arguments, dbt_example, monkeypatch):
    monkeypatch.delenv("EXTRA_PROJECT_DIR", raising=False)
    monkeypatch.chdir(dbt_example)
    before = snapshot(dbt_example)
    result = CliRunner().invoke(cli, arguments)
    assert result.exit_code == 0, result.output
    after = snapshot(dbt_example)
    assert after == before
