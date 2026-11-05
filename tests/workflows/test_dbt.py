"""dbt workflows: offline artifacts optional; authored files authoritative."""

from collections import Counter
import csv
import json
from pathlib import Path

from click.testing import CliRunner
import duckdb
from openpyxl import load_workbook
import pytest

from dbt_extra.cli import cli
from dbt_extra.analysis import analyze
from dbt_extra.files.changes import ChangeSet
from dbt_extra.enrichment import enrich
from dbt_extra.optimization import optimize, optimize_source
from dbt_extra.validation import validate
from dbt_extra.project import Project
from dbt_extra.review import export_review, import_review
from dbt_extra.review.import_ import read_review
from dbt_extra.inspection import inspect
from dbt_extra.sql import parse_authored, render
from dbt_extra.sql.jinja import validate_template
from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import load_yaml


from tests.helpers import edit_csv, invoke, project, put, snapshot


def test_optional_config_and_single_root_paths(native, monkeypatch):
    monkeypatch.delenv("EXTRA_PROJECT_DIR", raising=False)
    p = project(native)
    assert p.find("orders").model_path == "models/slv"
    assert p.find("revenue").model_path == "models/gld"
    put(native, "models/root_model.sql", "select 1 as id")
    assert project(native).find("root_model").model_path == "models"
    monkeypatch.chdir(native / "models/gld")
    assert Project(dialect="duckdb").root == native


def test_multiple_roots_preserve_project_relative_paths(native):
    put(native, "dbt_project.yml", "name: shop\nmodel-paths: [models, reporting]\n")
    put(native, "reporting/finance/profit.sql", "select 1 as profit")
    put(native, "reporting/root_model.sql", "select 1 as id")
    p = project(native)
    assert p.find("orders").model_path == "models/slv"
    assert p.find("profit").model_path == "reporting/finance"
    assert p.find("root_model").model_path == "reporting"


def test_all_resource_paths_include_parent_folders(native):
    put(native, "macros/helpers/math.sql", "{% macro double(value) %}{{ value }} * 2{% endmacro %}")
    put(native, "macros/schema.yml", "version: 2\nmacros:\n  - name: double\n    description: Twice the input\n")
    put(native, "seeds/reference.csv", "id\n1\n")
    put(native, "snapshots/history.sql", "{% snapshot history %}select 1 as id{% endsnapshot %}")
    p = project(native)
    resources = {r.name: r for r in p.resources.values()}
    assert resources["math"].model_path == "macros/helpers"
    assert resources["double"].model_path == "macros"
    assert resources["reference"].model_path == "seeds"
    assert resources["history"].model_path == "snapshots"
    assert p.resources["source.shop.raw.orders"].model_path == "models"
    assert p.resources["source_group.shop.raw"].model_path == "models"
    assert resources["math"].source_file == "macros/helpers/math.sql"


def test_cli_config_override_replaces_lists(native):
    put(native, "extra_project.yaml", "version: 2\nanalysis: {dialect: duckdb}\nexport:\n  format: csv\n  select: [orders]\n  output_dir: review\n")
    result = CliRunner().invoke(cli, ["--project-dir", str(native), "export", "-s", "revenue"])
    assert result.exit_code == 0, result.output
    with (native / "review/resources.csv").open(encoding="utf-8-sig") as stream:
        assert [r["name"] for r in csv.DictReader(stream)] == ["revenue"]


def test_views_and_path_selectors(native):
    put(native, "extra_project.yaml", "version: 2\nexport:\n  format: json\n  default_view: finance\n  views:\n    finance:\n      select: ['path:models/gld/**']\n")
    p = project(native)
    assert p.options("export")["select"] == ["path:models/gld/**"]
    assert [r.name for r in p.select(["path:models/gld/**"])] == ["revenue"]
    assert [r.name for r in p.select(["tag:slv"])] == ["orders"]


@pytest.mark.parametrize("format", ["xlsx", "csv", "json"])
def test_export_preview_writes_nothing(native, format):
    before = snapshot(native)
    result = invoke(native, "export", "--format", format, "--preview")
    assert result.exit_code == 0, result.output
    assert "Preview:" in result.output
    assert snapshot(native) == before


@pytest.mark.parametrize("format", ["xlsx", "csv"])
def test_noop_review_import_is_byte_preserving(native, format):
    p = project(native)
    export_review(p, format=format)
    before = snapshot(native)
    path = native / "extra_review" / "review.xlsx" if format == "xlsx" else native / "extra_review"
    changes = import_review(p, path)
    assert changes.apply() == []
    assert snapshot(native) == before


@pytest.mark.parametrize("format", ["xlsx", "csv", "json"])
def test_path_representation_matches_across_formats(native, format):
    export_review(project(native), format=format)
    if format == "json":
        items = json.loads((native / "extra_review/review.json").read_text())["resources"]
    elif format == "csv":
        with (native / "extra_review/resources.csv").open(encoding="utf-8-sig") as stream:
            items = list(csv.DictReader(stream))
    else:
        items = read_review(native / "extra_review/review.xlsx")[0]["resources"]
    assert next(r for r in items if r["name"] == "revenue")["model_path"] == "models/gld"


def test_metadata_roundtrip_preserves_yaml_comments_tests_and_source_groups(native):
    p = project(native)
    export_review(p, format="csv")
    review = native / "extra_review"
    edit_csv(review, "resources", lambda r: r["resource_id"] == "model.shop.orders", description="Reviewed orders")
    edit_csv(review, "resources", lambda r: r["resource_type"] == "source_group", properties='{"database": "new_landing"}')
    edit_csv(review, "columns", lambda r: r["resource_id"] == "model.shop.revenue" and r["column"] == "id",
             description="Reviewed identifier", properties='{"data_tests": ["not_null", "unique"]}')
    changes = import_review(project(native), review)
    before = snapshot(native)
    assert changes.apply(preview=True) == [native / "models/schema.yml"]
    assert snapshot(native) == before
    changes.apply()
    text = (native / "models/schema.yml").read_text()
    assert "# Keep this comment" in text and "# preserve inline comment" in text
    document = load_yaml(native / "models/schema.yml")
    assert document["sources"][0]["database"] == "new_landing"
    assert len(document["sources"][0]["tables"]) == 1
    assert document["models"][0]["description"] == "Reviewed orders"
    assert document["models"][1]["columns"][0]["data_tests"] == ["not_null", "unique"]


def test_stale_workbook_rejected_without_writes(native):
    export_review(project(native), format="csv")
    review = native / "extra_review"
    edit_csv(review, "resources", lambda r: r["name"] == "orders" and r["resource_type"] == "model", description="Changed")
    with (native / "models/slv/orders.sql").open("a") as stream:
        stream.write("-- Concurrent change\n")
    before = snapshot(native)
    with pytest.raises(SpecError, match="changed since export"):
        import_review(project(native), review)
    assert snapshot(native) == before


def test_readonly_path_edits_rejected(native):
    export_review(project(native), format="csv")
    edit_csv(native / "extra_review", "resources", lambda r: r["name"] == "revenue", model_path="other")
    with pytest.raises(SpecError, match="Read-only field"):
        import_review(project(native), native / "extra_review")


def test_expression_roundtrip_keeps_jinja_and_output_alias(native):
    export_review(project(native), format="csv")
    edit_csv(native / "extra_review", "columns", lambda r: r["resource_id"] == "model.shop.revenue" and r["column"] == "revenue", expression="amount * 2")
    changes = import_review(project(native), native / "extra_review")
    changes.apply()
    code = (native / "models/gld/revenue.sql").read_text()
    assert "{{ config(materialized='table') }}" in code
    assert "{{ ref('orders') }}" in code
    assert "amount * 2 AS revenue" in code


def test_full_source_roundtrip_opaque_macro(native):
    put(native, "models/dynamic.sql", "select {{ opaque_macro('amount') }} as amount")
    export_review(project(native), format="csv")
    edit_csv(native / "extra_review", "resources", lambda r: r["name"] == "dynamic", sql="select {{ opaque_macro('price') }} as amount\n")
    import_review(project(native), native / "extra_review").apply()
    assert "opaque_macro('price')" in (native / "models/dynamic.sql").read_text()


def test_xlsx_formula_rejected_and_text_literals_safe(native):
    put(native, "models/formula.sql", "select 1 as id")
    export_review(project(native), format="xlsx")
    path = native / "extra_review/review.xlsx"
    book = load_workbook(path)
    sheet = book["Models"]
    sheet["L2"] = "=1+1"
    book.save(path)
    book.close()
    with pytest.raises(SpecError, match="Formula"):
        import_review(project(native), path)


def test_optimize_source_without_artifacts_preserves_templates(native):
    p = project(native)
    before = snapshot(native)
    result = invoke(native, "optimize", "-s", "revenue", "--preview")
    assert result.exit_code == 0, result.output
    assert "--- models/gld/revenue.sql" in result.output
    assert snapshot(native) == before
    changes, skipped = optimize(p, select=["revenue"])
    assert not skipped
    changes.apply()
    code = (native / "models/gld/revenue.sql").read_text()
    assert "{{ config(materialized='table') }}" in code
    assert "{{ ref('orders') }}" in code
    assert not (native / "target").exists()
    assert not optimize(project(native), select=["revenue"])[0].changed()


@pytest.mark.parametrize("code", [
    "select {{ macro('x') }} as x", "{% if execute %}select 1{% else %}select 2{% endif %}",
    "select * from {{ ref(var('model')) }}", "select random() as x", "select udf(1) as x",
    "{{- config(materialized='view') -}}select 1 as id",
])
def test_unsafe_optimization_is_skipped(native, code):
    put(native, "models/unsafe.sql", code)
    changes, skipped = optimize(project(native), select=["unsafe"])
    assert not changes.changed()
    assert "model.shop.unsafe" in skipped


def test_reference_variants_and_config_preserved():
    code = "{{ config(materialized='view', meta={'owner': 'finance'}) }}\nselect id from {{ ref('pkg', 'orders', version=2) }} join {{ source('raw', 'users') }} u using (id)"
    # An unknown joined input may also contain id. Documentation is not an
    # exhaustive schema; the standalone API requires explicit complete evidence.
    from dbt_extra.sql.parser import parse_authored
    schema = {token: {"id": "INT"} for token in parse_authored(code, "duckdb").refs}
    optimized = optimize_source(code, "duckdb", schema=schema)
    assert "{{ ref('pkg', 'orders', version=2) }}" in optimized
    assert "{{ source('raw', 'users') }}" in optimized
    assert code.split("\n")[0] in optimized


def test_inspect_selected_preserves_rows_and_boundaries(native):
    p = project(native)
    tree, parsed, issues = inspect(p, "revenue", ["revenue"], compiled=False)
    assert "{{ source('raw', 'orders') }}" in render(tree, parsed, "duckdb")
    bounded, refs, _ = inspect(p, "revenue", ["revenue"], boundaries=["orders"])
    assert "{{ ref('orders') }}" in render(bounded, refs, "duckdb")
    assert "{{ source('raw', 'orders') }}" not in render(bounded, refs, "duckdb")
    with pytest.raises(SpecError, match="not upstream"):
        inspect(p, "orders", boundaries=["revenue"])
    con = duckdb.connect()
    try:
        con.execute("create table raw_orders(id int, amount int)")
        con.execute("insert into raw_orders values (1,2),(1,2),(2,-1),(3,10)")
        query = render(tree, parsed, "duckdb").replace("{{ source('raw', 'orders') }}", "raw_orders")
        expected = con.execute("select amount from raw_orders where amount >= 0 and amount > 1").fetchall()
        assert Counter(con.execute(query).fetchall()) == Counter(expected)
    finally:
        con.close()


@pytest.mark.parametrize("query", [
    "select distinct id, amount from {{ ref('orders') }}",
    "select id, amount from {{ ref('orders') }} union select id, amount from {{ ref('orders') }}",
    "select o.id, p.amount from {{ ref('orders') }} o left join {{ ref('orders') }} p on o.id=p.id where o.amount > 1",
])
def test_column_inspection_bag_equivalence(native, query):
    put(native, "models/target.sql", query)
    p = project(native)
    tree, refs, _ = inspect(p, "target", ["id"], compiled=False)
    full, full_refs, _ = inspect(p, "target", optimized=False, compiled=False)
    con = duckdb.connect()
    try:
        con.execute("create table raw_orders(id int, amount int)")
        con.execute("insert into raw_orders values (1,2),(1,2),(1,4),(2,0)")
        actual = render(tree, refs, "duckdb").replace("{{ source('raw', 'orders') }}", "raw_orders").rstrip(";\n")
        expected = render(full, full_refs, "duckdb").replace("{{ source('raw', 'orders') }}", "raw_orders").rstrip(";\n")
        assert Counter(con.execute(actual).fetchall()) == Counter(con.execute(f"select id from ({expected}) q").fetchall())
    finally:
        con.close()


def test_incremental_boundary_and_macro_coverage(native):
    put(native, "models/slv/orders.sql", "{{ config(materialized='incremental') }}\nselect id, amount from {{ source('raw','orders') }}")
    tree, refs, issues = inspect(project(native), "revenue")
    assert any("incremental" in i["reason"] for i in issues)
    assert "{{ ref('orders') }}" in render(tree, refs, "duckdb")


def test_enrich_passthrough_only_and_fill_missing(native):
    p = project(native)
    changes, report = enrich(p, select=["revenue"])
    assert any(r.get("value") == "Order identifier" for r in report)
    assert not any(r.get("value") == "Order amount" and r.get("column") == "revenue" for r in report)
    changes.apply()
    r = project(native).find("revenue")
    assert r.columns["id"]["description"] == "Order identifier"
    assert r.columns["id"]["data_type"].lower() == "bigint"


def test_manifest_names_and_staleness_do_not_rewrite_compiled_sql(native):
    manifest = {"metadata": {"adapter_type": "duckdb"}, "nodes": {"model.shop.renamed": {
        "name": "renamed", "resource_type": "model", "package_name": "shop", "original_file_path": "models/gld/revenue.sql",
        "raw_code": "select 999 as revenue", "compiled_code": "delete from production"}}}
    put(native, "target/manifest.json", json.dumps(manifest))
    p = Project(native)
    assert p.find("renamed").model_path == "models/gld"
    assert any(i["code"] == "SOURCE_CHANGED" for i in p.diagnostics)
    changes, skipped = optimize(p, select=["renamed"])
    assert not skipped
    assert "delete" not in next(iter(changes.changed().values())).decode().lower()


def test_missing_dialect_is_explicit(native):
    p = Project(native)
    with pytest.raises(SpecError, match="requires --dialect"):
        optimize(p)
    assert analyze(p, p.find("orders"))["status"] == "unavailable"


def test_checked_writes_rollback_on_replace_failure(native, monkeypatch):
    import dbt_extra.files.changes as edits
    a, b = native / "models/slv/orders.sql", native / "models/gld/revenue.sql"
    before = snapshot(native)
    changes = ChangeSet(native)
    changes.set(a, "select 1 as id")
    changes.set(b, "select 2 as id")
    replace, count = edits.os.replace, 0
    def fail(source, destination):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("simulated failure")
        replace(source, destination)
    monkeypatch.setattr(edits.os, "replace", fail)
    with pytest.raises(OSError, match="simulated"):
        changes.apply()
    assert snapshot(native) == before


def test_validate_cycles_and_invalid_sql(native):
    put(native, "models/slv/orders.sql", "select id from {{ ref('revenue') }}")
    with pytest.raises(SpecError, match="Cyclic"):
        validate(project(native))
    put(native, "models/slv/orders.sql", "delete from x")
    with pytest.raises(SpecError, match="read-only"):
        validate(project(native))


def test_macro_snapshot_and_source_metadata_roundtrip(native):
    put(native, "macros/math.sql", "{% macro double(value) %}{{ value }} * 2{% endmacro %}")
    put(native, "macros/schema.yml", "version: 2\nmacros:\n  - name: double\n    description: Twice the value\n")
    put(native, "snapshots/schema.yml", "version: 2\nsnapshots:\n  - name: history\n    relation: ref('orders')\n    config: {strategy: timestamp, updated_at: updated_at, unique_key: id}\n")
    put(native, "snapshots/old.sql", "{% snapshot old %}{{ config(strategy='check', unique_key='id') }}select 1 as id{% endsnapshot %}")
    p = project(native)
    assert any(r.kind == "snapshot" and r.name == "history" for r in p.resources.values())
    export_review(p, format="csv")
    edit_csv(native / "extra_review", "resources", lambda r: r["resource_type"] == "macro_definition", description="Double the input")
    import_review(project(native), native / "extra_review").apply()
    assert load_yaml(native / "macros/schema.yml")["macros"][0]["description"] == "Double the input"
    validate_template((native / "snapshots/old.sql").read_text())


def test_only_dbt_public_commands():
    assert set(cli.commands) == {"init", "validate", "inspect", "export", "import", "optimize", "enrich"}


@pytest.mark.parametrize("dialect", ["duckdb", "postgres", "snowflake", "bigquery", "spark", "tsql"])
def test_source_rewrite_roundtrips_across_dialects(dialect):
    code = "-- Authored header\n{{ config(materialized='view') }}\nselect o.id, o.amount + 0 as amount from {{ ref('orders') }} o where o.id > 0\n"
    candidate = optimize_source(code, dialect)
    assert candidate.startswith("-- Authored header\n{{ config(materialized='view') }}")
    assert candidate.count("-- Authored header") == 1
    assert candidate.count("{{ ref('orders') }}") == 1
    assert "extra_ref_" not in candidate
    assert optimize_source(candidate, dialect) == candidate


@pytest.mark.parametrize("dialect", ["duckdb", "postgres", "snowflake", "bigquery", "spark", "tsql"])
def test_selected_inspection_roundtrips_across_dialects(native, dialect):
    p = Project(native, dialect=dialect)
    tree, refs, _ = inspect(p, "revenue", ["revenue"], compiled=False)
    query = render(tree, refs, dialect)
    assert "{{ source('raw', 'orders') }}" in query
    assert len(parse_authored(query, dialect).tree.selects) == 1


@pytest.mark.parametrize("optimized", [True, False])
@pytest.mark.parametrize("rows", [[], [(1, 2)], [(1, 2), (1, 2), (2, 5)]])
def test_global_aggregate_inspection_preserves_one_row(native, optimized, rows):
    put(native, "models/target.sql", "select 7 as marker, count(*) as total from {{ ref('orders') }}")
    p = project(native)
    tree, refs, _ = inspect(p, "target", ["marker"], optimized=optimized, compiled=False)
    query = render(tree, refs, "duckdb").replace("{{ source('raw', 'orders') }}", "raw_orders")
    con = duckdb.connect()
    try:
        con.execute("create table raw_orders(id int, amount int)")
        if rows:
            con.executemany("insert into raw_orders values (?, ?)", rows)
        assert con.execute(query).fetchall() == [(7,)]
    finally:
        con.close()


def test_wildcard_requires_evidence_and_does_not_invent_metadata(native):
    put(native, "models/target.sql", "select * from {{ ref('orders') }}")
    p = project(native)
    analysis = analyze(p, p.find("target"))
    assert {c["name"] for c in analysis["columns"]} == {"id", "amount"}
    tree, refs, _ = inspect(p, "target", ["amount"])
    assert len(tree.selects) == 1
    put(native, "models/unknown.sql", "select * from {{ ref('not_loaded') }}")
    p = project(native)
    assert analyze(p, p.find("unknown"))["status"] == "partial"
    with pytest.raises(SpecError, match="unresolved"):
        inspect(p, "unknown", ["amount"])


def test_unknown_join_schema_does_not_supply_false_lineage(native):
    put(native, "models/unknown.sql", "select amount as value from {{ ref('orders') }} o join {{ ref('not_loaded') }} x on o.id=x.id")
    p = project(native)
    result = analyze(p, p.find("unknown"))
    assert result["status"] == "partial"
    column = next(c for c in result["columns"] if c["name"] == "value")
    assert column["upstream_columns"] == []
    assert not column.get("inferred_type")


def test_clearing_last_metadata_field_is_applied(native):
    put(native, "models/bare.sql", "select 1 as id")
    put(native, "models/bare.yml", "version: 2\nmodels:\n  - name: bare\n    description: Remove this\n")
    export_review(project(native), format="csv")
    edit_csv(native / "extra_review", "resources", lambda r: r["name"] == "bare", description="")
    import_review(project(native), native / "extra_review").apply()
    assert "description" not in load_yaml(native / "models/bare.yml")["models"][0]


def test_project_config_changes_invalidate_edits(native):
    export_review(project(native), format="csv")
    edit_csv(native / "extra_review", "resources", lambda r: r["name"] == "revenue", description="Reviewed")
    with (native / "dbt_project.yml").open("a") as stream:
        stream.write("# Concurrent configuration change\n")
    before = snapshot(native)
    with pytest.raises(SpecError, match="changed since export"):
        import_review(project(native), native / "extra_review")
    assert snapshot(native) == before


def test_config_directory_can_point_at_nested_dbt_project(tmp_path):
    put(tmp_path, "extra_project.yaml", "version: 2\ndbt:\n  project_dir: project\nanalysis:\n  dialect: duckdb\n")
    put(tmp_path, "project/dbt_project.yml", "name: nested\n")
    put(tmp_path, "project/models/one.sql", "select 1 as id")
    p = Project(tmp_path)
    assert p.root == tmp_path / "project"
    assert p.find("one").model_path == "models"


def test_external_tool_settings_are_checked_for_conflicts(tmp_path):
    config = put(tmp_path, "extra_project.yaml", "version: 2\ndbt:\n  project_dir: project\nanalysis:\n  dialect: duckdb\n")
    put(tmp_path, "project/dbt_project.yml", "name: nested\n")
    put(tmp_path, "project/models/one.sql", "select 1 as id")
    p = Project(tmp_path)
    export_review(p, format="csv")
    edit_csv(p.root / "extra_review", "columns", lambda r: r["column"] == "id", description="Identifier")
    changes, _ = optimize(p)
    config.write_text(config.read_text() + "# Concurrent change\n")
    with pytest.raises(SpecError, match="changed while preparing"):
        changes.apply()
    with pytest.raises(SpecError, match="changed since export"):
        import_review(Project(tmp_path), p.root / "extra_review")


def test_export_rejects_changes_after_project_load(native):
    p = project(native)
    put(native, "models/gld/revenue.sql", "select 1 as revenue")
    before = snapshot(native)
    with pytest.raises(SpecError, match="changed while preparing export"):
        export_review(p, format="csv")
    assert snapshot(native) == before


def test_yaml_anchors_refuse_writeback(native):
    put(native, "models/anchored.yml", "version: 2\nmodels:\n  - &shared\n    name: anchored\n    description: Shared\n")
    put(native, "models/anchored.sql", "select 1 as id")
    export_review(project(native), format="csv")
    edit_csv(native / "extra_review", "resources", lambda r: r["name"] == "anchored", description="Changed")
    before = snapshot(native)
    with pytest.raises(SpecError, match="anchors"):
        import_review(project(native), native / "extra_review")
    assert snapshot(native) == before


def test_staged_writes_reject_concurrent_source_change(native):
    changes, _ = optimize(project(native), select=["revenue"])
    put(native, "models/gld/revenue.sql", "select 99 as id")
    before = snapshot(native)
    with pytest.raises(SpecError, match="changed while preparing"):
        changes.apply()
    assert snapshot(native) == before


@pytest.mark.parametrize("code", ["delete from {{ ref('orders') }}", "select 1 as id; select 2 as id"])
def test_invalid_static_jinja_sql_is_not_misreported_as_opaque(native, code):
    put(native, "models/invalid.sql", code)
    with pytest.raises(SpecError):
        validate(project(native))


def test_xlsx_rejects_large_cells_before_openpyxl_can_truncate(native):
    put(native, "models/large.sql", "select '" + "x" * 33000 + "' as payload")
    before = snapshot(native)
    with pytest.raises(SpecError, match="XLSX cell limit"):
        export_review(project(native), format="xlsx")
    assert snapshot(native) == before
    export_review(project(native), format="csv")
    assert import_review(project(native), native / "extra_review").changed() == {}


def test_render_markers_cannot_replace_authored_string_literals(native):
    code = "select 'EXTRA_RENDER_RELATION_0' as marker, id from {{ ref('orders') }}"
    put(native, "models/markers.sql", code)
    candidate = optimize_source(code, "duckdb")
    assert "'EXTRA_RENDER_RELATION_0'" in candidate
    tree, parsed, _ = inspect(project(native), "markers", ["marker"], expanded=False, optimized=False)
    explained = render(tree, parsed, "duckdb")
    assert "'EXTRA_RENDER_RELATION_0'" in explained
    assert explained.count("{{ ref('orders') }}") == 1
    parse_authored(explained, "duckdb")


def test_dynamic_config_is_preserved_but_prevents_upstream_expansion(native):
    code = "{{ config(materialized=var('storage')) }}\nselect id, amount from {{ source('raw', 'orders') }}"
    put(native, "models/slv/orders.sql", code)
    assert "{{ config(materialized=var('storage')) }}" in optimize_source(code, "duckdb")
    tree, parsed, issues = inspect(project(native), "revenue", ["revenue"])
    assert "{{ ref('orders') }}" in render(tree, parsed, "duckdb")
    assert any("dynamic configuration" in issue["reason"] for issue in issues)


def test_deleting_anchored_scalar_requires_manual_metadata_edit(native):
    put(native, "models/anchored.sql", "select 1 as id")
    put(native, "models/anchored.yml", "version: 2\nmodels:\n  - name: anchored\n    description: &shared Shared\n")
    export_review(project(native), format="csv")
    edit_csv(native / "extra_review", "resources", lambda row: row["name"] == "anchored", description="")
    before = snapshot(native)
    with pytest.raises(SpecError, match="anchors"):
        import_review(project(native), native / "extra_review")
    assert snapshot(native) == before


def test_manifest_from_another_project_is_not_silent_evidence(native):
    put(native, "target/manifest.json", json.dumps({"metadata": {"project_name": "other", "adapter_type": "duckdb"}}))
    with pytest.raises(SpecError, match="does not match dbt project"):
        project(native)


def test_export_cli_expand_and_named_view(native):
    put(native, "macros/fields.sql", "{% macro fields() %}id, amount as total{% endmacro %}")
    put(native, "models/multi.sql", "select {{ fields() }} from {{ ref('orders') }}")
    result = invoke(native, "export", "--expand", "-s", "multi")
    assert result.exit_code == 0, result.output
    tables, baseline = read_review(native / "extra_review/review.xlsx")
    assert baseline["expanded_macros"]
    assert {c["column"] for c in tables["columns"]} == {"id", "total"}
    put(native, "extra_project.yaml", "version: 2\nexport:\n  views:\n    expanded:\n      select: [multi]\n      expand: true\n")
    assert invoke(native, "export", "--view", "expanded").exit_code == 0
    assert read_review(native / "extra_review/review.xlsx")[1]["expanded_macros"]
    assert invoke(native, "export", "--view", "expanded", "--no-expand").exit_code == 0
    assert not read_review(native / "extra_review/review.xlsx")[1]["expanded_macros"]


def test_expanded_csv_expressions_are_readonly_but_metadata_is_editable(native):
    put(native, "macros/fields.sql", "{% macro fields() %}id, amount as total{% endmacro %}")
    put(native, "models/multi.sql", "select {{ fields() }} from {{ ref('orders') }}")
    export_review(project(native), format="csv", select=["multi"], expand=True)
    review = native / "extra_review"
    edit_csv(review, "columns", lambda r: r["column"] == "total", description="Generated total")
    import_review(project(native), review).apply()
    export_review(project(native), format="csv", select=["multi"], expand=True)
    edit_csv(review, "columns", lambda r: r["column"] == "total", expression="amount * 99")
    with pytest.raises(SpecError, match="read-only"):
        import_review(project(native), review)
