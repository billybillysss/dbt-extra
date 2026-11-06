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
from dbt_extra.analysis import analyze, catalog
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
        assert not target.is_relative_to(ROOT / "local"), f"{path}: public link to owner-only notes: {href}"
        assert target.exists(), f"{path}: missing local link: {href}"
        if parsed.fragment and target.suffix == ".md":
            assert unquote(parsed.fragment) in anchors(target.read_text(encoding="utf-8")), f"{path}: missing anchor: {href}"


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_json_examples_parse(path):
    for block in blocks(path.read_text(encoding="utf-8"), "json"):
        json.loads(block)


@pytest.mark.parametrize("example", [0, 1])
def test_function_semantics_examples_match_the_optimizer(example):
    from dbt_extra.sql.rewrites.engine import optimize_source

    text = (ROOT / "docs/reference/sql-functions/README.md").read_text(encoding="utf-8")
    section = text.split("## Why dbt-extra defines SQL function semantics\n", 1)[1].split("\n## ", 1)[0]
    examples = blocks(section, "sql")
    assert len(examples) == 4
    before, after = examples[example * 2:example * 2 + 2]
    assert optimize_source(before, "spark", schema={"t": {"id": "BIGINT"}}).strip() == after.strip()


@pytest.mark.parametrize("document, heading", [
    ("docs/reference/configuration.md", "# Project configuration\n"),
    ("README.md", "## Configure an existing project\n"),
])
def test_documented_config_and_native_example(tmp_path, document, heading):
    configuration = (ROOT / document).read_text(encoding="utf-8").split(heading, 1)[1]
    example = tmp_path / "settings.yml"
    example.write_text(blocks(configuration, "yaml")[0], encoding="utf-8")
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


@pytest.mark.parametrize("document, heading", [
    ("docs/getting-started.md", "## See where a column comes from\n"),
    ("README.md", "### Preserve filters and grouping\n"),
])
def test_documented_inspection_sql_matches_cli(dbt_example, document, heading):
    before = snapshot(dbt_example)
    result = CliRunner().invoke(cli, ["--project-dir", str(dbt_example), "inspect",
        "customer_revenue", "--columns", "revenue"])
    assert result.exit_code == 0, result.output
    query = "\n".join(line for line in result.output.splitlines() if not line.startswith("--"))
    section = (ROOT / document).read_text(encoding="utf-8").split(heading, 1)[1].split("\n## ", 1)[0]
    shown = blocks(section, "sql")
    assert len(shown) == 1
    assert shown[0].strip() == query.strip()
    assert snapshot(dbt_example) == before


def test_readme_column_trace_matches_project_and_cli(dbt_example):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("### Trace a column through multiple dbt layers\n", 1)[1].split("\n### ", 1)[0]
    shown = blocks(section, "sql")
    names = ["stg_customers", "customer_details", "customer_profile"]
    assert len(shown) == 5
    for name, sql in zip(names, shown[2:]):
        folder = "gld" if name == "customer_profile" else "slv"
        assert (dbt_example / f"models/{folder}/{name}.sql").read_text(encoding="utf-8").strip() == sql.strip()

    before = snapshot(dbt_example)
    runner = CliRunner()
    arguments = ["--project-dir", str(dbt_example), "inspect", "customer_profile", "--columns", "customer_name"]
    result = runner.invoke(cli, arguments)
    assert result.exit_code == 0, result.output
    query = "\n".join(line for line in result.output.splitlines() if not line.startswith("--"))
    assert query.strip() == shown[0].strip()
    assert blocks(readme, "sql")[0].strip() == query.strip()
    assert "{{" not in query
    assert "main_raw.raw_customers" in query
    assert 'TRIM("customers".first_name)' in query
    assert "WITH" not in query and "FROM (" not in query

    expanded = runner.invoke(cli, [*arguments, "--optimize", "false"])
    assert expanded.exit_code == 0, expanded.output
    expanded_query = "\n".join(line for line in expanded.output.splitlines() if not line.startswith("--"))
    assert expanded_query.strip() == shown[1].strip()
    assert "first_name AS customer_name" in expanded.output
    assert "TRIM(first_name) AS first_name" in expanded.output
    assert "WITH customer_input" in expanded.output
    expanded_tree = parse_authored(expanded.output, "duckdb").tree
    assert expanded_tree.args["from_"].this.this.named_selects == [
        "customer_id", "customer_name", "last_name",
    ]
    assert snapshot(dbt_example) == before


@pytest.mark.parametrize("name, column, upstream_id, upstream_column, expression", [
    ("customer_profile", "customer_name", "model.jaffle_shop.customer_details", "first_name", "first_name"),
    ("customer_details", "first_name", "model.jaffle_shop.stg_customers", "first_name", "first_name"),
    ("stg_customers", "first_name", "source.jaffle_shop.jaffle_shop.customers", "first_name", "TRIM(first_name)"),
])
def test_readme_column_trace_lineage_matches_analysis(dbt_example, name, column, upstream_id, upstream_column, expression):
    project = Project(dbt_example)
    columns = analyze(project, project.find_model(name), expand=True)["columns"]
    selected = next(item for item in columns if item["name"] == column)
    assert selected["status"] == "resolved"
    assert selected["expression"] == expression
    assert selected["upstream_columns"] == [{"resource_id": upstream_id, "column": upstream_column}]


def test_documented_selected_column_simplification_matches_cli(dbt_example, monkeypatch):
    monkeypatch.delenv("EXTRA_PROJECT_DIR", raising=False)
    monkeypatch.chdir(dbt_example)
    guide = (ROOT / "docs/guides/inspection-and-optimization.md").read_text(encoding="utf-8")
    section = guide.split("### Simplify the logic for one selected column\n", 1)[1].split("\n## ", 1)[0]
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
    assert 'SUM("orders".amount)' in shown[1]
    assert 'GROUP BY\n    "orders".customer_id' in shown[1]
    assert 'order_totals.revenue + 0 AS "revenue"' in shown[1]


@pytest.mark.parametrize("document, heading", [
    ("docs/guides/metadata-enrichment.md", "## YAML proposal\n"),
    ("README.md", "## Fill missing column metadata\n"),
])
def test_documented_enrichment_yaml_matches_real_proposal(dbt_example, tmp_path, document, heading):
    guide = (ROOT / document).read_text(encoding="utf-8")
    section = guide.split(heading, 1)[1].split("\n## ", 1)[0]
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


@pytest.mark.parametrize("document, heading", [
    ("docs/reference/configuration.md", "# Project configuration\n"),
    ("README.md", "## Configure an existing project\n"),
])
def test_documented_settings_support_named_view_and_workflow_defaults(dbt_example, document, heading):
    configuration = (ROOT / document).read_text(encoding="utf-8").split(heading, 1)[1]
    settings = blocks(configuration, "yaml")[0]
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


def test_documented_json_example_includes_explicit_upstream_context(dbt_example):
    result = CliRunner().invoke(cli, ["--project-dir", str(dbt_example), "export", "--format", "json",
        "--select", "customer_revenue", "orders", "demo_raw_orders", "--output-dir", "extra/review-json"])
    assert result.exit_code == 0, result.output
    document = json.loads((dbt_example / "extra/review-json/review.json").read_text(encoding="utf-8"))
    assert document["format_version"] == 1
    assert document["source_of_truth"] == "dbt"
    assert {resource["name"] for resource in document["resources"]} == {
        "customer_revenue", "orders", "demo_raw_orders",
    }


@pytest.mark.parametrize("document", ["docs/guides/catalog-round-trip.md", "README.md"])
def test_documented_description_review_round_trip(dbt_example, document):
    """Follow the Excel guide on a disposable project, never the teaching inputs."""
    runner = CliRunner()
    arguments = ["--project-dir", str(dbt_example)]
    original = snapshot(dbt_example)
    result = runner.invoke(cli, [*arguments, "export", "--format", "xlsx", "--select", "customer_revenue"])
    assert result.exit_code == 0, result.output
    workbook = dbt_example / "extra/review/review.xlsx"
    guide = (ROOT / document).read_text(encoding="utf-8")
    if document == "README.md":
        guide = guide.split("## Review and edit in Excel\n", 1)[1].split("\n## ", 1)[0]
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


def test_five_step_demo_sql_matches_inspection_and_source_proposal(dbt_example):
    from dbt_extra.optimization import optimize

    guide = (ROOT / "docs/guides/five-step-demo.md").read_text(encoding="utf-8")
    shown = blocks(guide, "sql")
    assert len(shown) == 3
    before = snapshot(dbt_example)
    result = CliRunner().invoke(cli, ["--project-dir", str(dbt_example), "inspect",
        "customer_profile", "--columns", "customer_name"])
    assert result.exit_code == 0, result.output
    query = "\n".join(line for line in result.output.splitlines() if not line.startswith("--"))
    assert query.strip() == shown[0].strip()

    project = Project(dbt_example)
    resource = project.find_model("gld_optimizer_projections")
    changes, skipped = optimize(project, select=[resource.name])
    assert not skipped
    original = resource.code.replace("\r\n", "\n")
    proposed = changes.changed()[resource.path].decode("utf-8").replace("\r\n", "\n")
    for code, expected in zip((original, proposed), shown[1:]):
        parsed = parse_authored(code, project.dialect)
        assert code.removeprefix(parsed.prefix).strip() == expected.strip()
    assert snapshot(dbt_example) == before


def test_five_step_demo_preserves_examples_and_cleans_temporary_files(dbt_example, tmp_path, monkeypatch, capsys):
    from scripts import demo_review

    before = snapshot(dbt_example)
    temporary = tmp_path / "demo"
    temporary.mkdir()
    monkeypatch.setattr(demo_review, "ROOT", dbt_example.parents[1])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXTRA_PROJECT_DIR", str(tmp_path / "not-a-project"))
    demo_review.main(["--temp-dir", str(temporary)])
    output = capsys.readouterr().out
    assert all(f"{step}/5 - " in output for step in range(1, 6))
    assert 'TRIM("customers".first_name)' in output
    assert "gld_optimizer_projections.sql" in output
    assert "Optimization SQL files written: 0" in output
    assert "models/schema.yml" in output.replace("\\", "/")
    assert f"+    description: {demo_review.DESCRIPTION}" in output
    assert "All original project files are unchanged" in output
    assert "Temporary demo files removed." in output
    assert snapshot(dbt_example) == before
    assert list(temporary.iterdir()) == []


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


@pytest.mark.parametrize("document", ["docs/reference/python-api.md", "README.md"])
def test_documented_python_api_is_read_only(monkeypatch, dbt_example, document):
    monkeypatch.delenv("EXTRA_PROJECT_DIR", raising=False)
    monkeypatch.chdir(dbt_example)
    before = snapshot(dbt_example)
    namespace = {}
    exec(blocks((ROOT / document).read_text(encoding="utf-8"), "python")[0], namespace)
    assert namespace["document"]["resources"][0]["name"] == "customer_revenue"
    assert not namespace["skipped"]
    if document == "README.md":
        assert 'AS "revenue"' in namespace["explanation"]
        assert "Logical plan" in namespace["logical_plan"]
        assert namespace["changes"].optimization_report
        assert sum("value" in item for item in namespace["report"]) == 4
    assert snapshot(dbt_example) == before


@pytest.mark.parametrize("document", ["docs/reference/python-api.md", "README.md"])
def test_documented_standalone_python_example(document):
    namespace = {}
    exec(blocks((ROOT / document).read_text(encoding="utf-8"), "python")[1], namespace)
    assert any(outcome["status"] == "applied" for outcome in namespace["outcomes"])


def test_readme_has_a_command_example_for_every_cli_feature():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    commands = "\n".join(blocks(readme, "bash"))
    for name in cli.commands:
        assert re.search(rf"^(?:uv run )?extra (?:--dialect \w+ )?{name}(?: |$)", commands, re.MULTILINE), name


def test_readme_cli_walkthrough_preserves_dbt_inputs(dbt_example, monkeypatch):
    """Check runnable syntax; the separate round-trip test supplies the Excel edit."""
    monkeypatch.delenv("EXTRA_PROJECT_DIR", raising=False)
    monkeypatch.chdir(dbt_example)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    before = snapshot(dbt_example)
    runner = CliRunner()
    for block in blocks(readme, "bash"):
        for line in block.splitlines():
            if not line.startswith("uv run extra "):
                continue
            arguments = shlex.split(line)[3:]
            previous = snapshot(dbt_example)
            result = runner.invoke(cli, arguments)
            assert result.exit_code == 0, f"{line}\n{result.output}"
            if arguments[0] in {"inspect", "validate"} or "--preview" in arguments:
                assert snapshot(dbt_example) == previous
    after = snapshot(dbt_example)
    assert all(after[path] == content for path, content in before.items())
    assert {path for path in after if path not in before} == {
        "extra/review/review.xlsx", "extra/review-expanded/review.xlsx",
        "extra/review-csv/resources.csv", "extra/review-csv/columns.csv",
        "extra/review-csv/_baseline.json", "extra/review-csv/README.txt",
        "extra/review-json/review.json",
    }


@pytest.mark.parametrize("heading, name, expand", [
    ("## Optimize authored SQL\n", "gld_optimizer_constants", False),
    ("### Expand static local macros and templates\n", "macro_revenue", True),
])
def test_readme_source_optimization_before_and_after(dbt_example, heading, name, expand):
    from dbt_extra.optimization import optimize

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = re.split(r"\n#{2,3} ", readme.split(heading, 1)[1], maxsplit=1)[0]
    shown = blocks(section, "sql")
    assert len(shown) == 2
    project = Project(dbt_example)
    resource = project.find_model(name)
    before = snapshot(dbt_example)
    changes, skipped = optimize(project, select=[name], expand=expand)
    assert not skipped
    original = resource.code.replace("\r\n", "\n")
    proposed = changes.changed()[resource.path].decode("utf-8").replace("\r\n", "\n")
    if expand:
        assert original.strip() == shown[0].strip()
        assert proposed.strip() == shown[1].strip()
    else:
        parsed_before = parse_authored(original, project.dialect)
        parsed_after = parse_authored(proposed, project.dialect)
        assert original.removeprefix(parsed_before.prefix).strip() == shown[0].strip()
        assert proposed.removeprefix(parsed_after.prefix).strip() == shown[1].strip()
        assert parsed_before.config == parsed_after.config
    assert snapshot(dbt_example) == before


def test_cli_reference_covers_commands_and_options():
    reference = (ROOT / "docs/reference/cli.md").read_text(encoding="utf-8")
    for name in cli.commands:
        assert f"## {name.title()}\n" in reference
    for command in [cli, *cli.commands.values()]:
        for parameter in command.params:
            for option in (*getattr(parameter, "opts", []), *getattr(parameter, "secondary_opts", [])):
                if option.startswith("-"):
                    assert option in reference, f"Undocumented option: {command.name} {option}"


def test_documented_optimization_rewrites_only_authored_sql(dbt_example):
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
