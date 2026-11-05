"""Metadata stays in memory until applied to an existing native dbt YAML entry."""

import copy
import json

import pytest

from dbt_extra.analysis import analyze
from dbt_extra.enrichment import enrich
from dbt_extra.errors import SpecError
from dbt_extra.files.changes import ChangeSet
from dbt_extra.files.yaml import load_yaml
from dbt_extra.review import export_review, import_review
from dbt_extra.review.import_ import read_review
from tests.helpers import edit_csv, invoke, project, put, snapshot


@pytest.mark.parametrize("kind, path, code", [
    ("model", "models/undocumented.sql", "select 1 as id"),
    ("seed", "seeds/undocumented.csv", "id\n1\n"),
    ("snapshot", "snapshots/undocumented.sql", "{% snapshot undocumented %}select 1 as id{% endsnapshot %}"),
])
def test_import_skips_missing_yaml_entries_without_creating_files(native, kind, path, code):
    put(native, path, code)
    p = project(native)
    export_review(p, format="csv", select=["undocumented"])
    review = native / "extra/review"
    edit_csv(review, "resources", lambda r: r["name"] == "undocumented", description="Reviewed")
    baseline = json.loads((review / "_baseline.json").read_text())
    assert set(baseline["files"]) == {"dbt_project.yml", path}
    before = snapshot(native)
    changes = import_review(project(native), review)
    uid = f"{kind}.shop.undocumented"
    assert "No existing writable dbt YAML entry" in changes.metadata_skipped[uid]
    assert changes.apply() == []
    assert snapshot(native) == before
    result = invoke(native, "import", str(review), "--preview")
    assert result.exit_code == 0, result.output
    assert f"Skipped metadata {uid}" in result.output
    assert snapshot(native) == before
    with pytest.raises(SpecError, match="No existing writable dbt YAML entry"):
        ChangeSet(native).properties(p, p.resources[uid], {"name": "undocumented", "description": "Reviewed"})
    assert snapshot(native) == before


def test_missing_metadata_does_not_block_supported_sql_edits(native):
    sql = put(native, "models/undocumented.sql", "select 1 as id")
    export_review(project(native), format="csv", select=["undocumented"])
    review = native / "extra/review"
    edit_csv(review, "resources", lambda r: True, description="Not persisted")
    edit_csv(review, "columns", lambda r: True, description="Identifier", data_type="bigint", expression="2")
    changes = import_review(project(native), review)
    assert set(changes.changed()) == {sql}
    assert "model.shop.undocumented" in changes.metadata_skipped
    changes.apply()
    assert "2 AS id" in sql.read_text()
    assert not project(native).find("undocumented").properties


def test_enrich_skips_missing_entry_and_reports_why(native):
    put(native, "models/undocumented.sql", "select id from {{ ref('orders') }}")
    p = project(native)
    before = snapshot(native)
    assert analyze(p, p.find("undocumented"))["columns"]
    changes, report = enrich(p, select=["undocumented"])
    assert len(report) == 1 and "No existing writable dbt YAML entry" in report[0]["reason"]
    assert changes.apply() == []
    result = invoke(native, "enrich", "-s", "undocumented", "--preview")
    assert result.exit_code == 0, result.output
    assert "Skipped metadata model.shop.undocumented" in result.output
    assert snapshot(native) == before


def test_enrich_can_inherit_through_undocumented_upstream_in_memory(native):
    put(native, "models/undocumented.sql", "select id from {{ ref('orders') }}")
    put(native, "models/downstream.sql", "select id from {{ ref('undocumented') }}")
    yaml = put(native, "models/downstream.yml", "version: 2\nmodels:\n  - name: downstream\n")
    changes, report = enrich(project(native), select=["downstream", "undocumented"])
    assert set(changes.changed()) == {yaml}
    assert any("No existing" in r.get("reason", "") for r in report)
    changes.apply()
    assert project(native).find("downstream").columns["id"]["description"] == "Order identifier"
    assert not project(native).find("undocumented").properties


@pytest.mark.parametrize("style", ["legacy", "column"])
def test_enrich_preserves_semantic_definitions_and_preview_is_readonly(native, style):
    put(native, "models/semantic.sql", "select id from {{ ref('orders') }}")
    metadata = """# Semantic definitions remain authored
version: 2
models:
  - name: semantic
    columns:
      - name: id
"""
    if style == "legacy":
        metadata += """semantic_models:
  - name: orders_semantic
    model: ref('semantic')
    entities:
      - name: order
        type: primary
        expr: id
    dimensions:
      - name: order_category
        type: categorical
        expr: id
    measures:
      - name: order_count
        agg: count
        expr: id
metrics:
  - name: orders
    label: Orders
    type: simple
    type_params:
      measure: order_count
"""
    else:
        metadata += """        entity:
          name: order
          type: primary
    semantic_model:
      enabled: true
    metrics:
      - name: orders
        type: simple
        label: Orders
        agg: count
        expr: id
"""
    yaml = put(native, "models/semantic.yml", metadata)
    before_document = load_yaml(yaml)
    before = snapshot(native)
    result = invoke(native, "enrich", "-s", "semantic", "--preview")
    assert result.exit_code == 0, result.output
    assert "Order identifier" in result.output
    assert snapshot(native) == before
    changes, _ = enrich(project(native), select=["semantic"])
    assert set(changes.changed()) == {yaml}
    assert snapshot(native) == before
    changes.apply()
    after = load_yaml(yaml)
    column = after["models"][0]["columns"][0]
    assert column["description"] == "Order identifier"
    assert column["data_type"].lower() == "bigint"
    expected = copy.deepcopy(before_document)
    expected["models"][0]["columns"][0].update(description=column["description"], data_type=column["data_type"])
    assert after == expected
    assert "# Semantic definitions remain authored" in yaml.read_text()
    assert not enrich(project(native), select=["semantic"])[0].changed()
    export_review(project(native), format="csv", select=["semantic"])
    review = native / "extra/review"
    edit_csv(review, "resources", lambda r: True, description="Reviewed model")
    import_review(project(native), review).apply()
    expected["models"][0]["description"] = "Reviewed model"
    assert load_yaml(yaml) == expected


def test_xlsx_baseline_uses_version_one_and_retains_file_hashes(native):
    export_review(project(native), select=["revenue"])
    path = native / "extra/review/review.xlsx"
    _, baseline = read_review(path)
    assert baseline["format_version"] == 1 and "format" not in baseline
    assert baseline["files"]["models/schema.yml"]
    assert import_review(project(native), path).apply() == []
