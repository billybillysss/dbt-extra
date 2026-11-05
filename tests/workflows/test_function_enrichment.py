"""Documented SQL functions produce the stated enrichment proposals offline."""

from pathlib import Path

import pytest
from sqlglot import exp

from dbt_extra.analysis import analyze
from dbt_extra.enrichment import enrich
from dbt_extra.project import Project
from tests.helpers import SQL_DIALECTS, put, snapshot


REFERENCE = Path(__file__).resolve().parents[2] / "docs/reference/sql-functions/README.md"


def documented_examples():
    section = REFERENCE.read_text(encoding="utf-8").split("## Verified examples\n", 1)[1].split("\n## ", 1)[0]
    cases = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        assert len(cells) == 3, line
        dialect, expression, result = cells
        assert dialect and expression and result, line
        cases.append(pytest.param(dialect, expression, None if result == "unresolved" else result,
                                  id=f"{dialect}-{expression}"))
    assert cases, "The function reference must contain executable examples"
    return cases


@pytest.mark.parametrize("dialect, expression, expected", documented_examples())
def test_documented_function_enrichment(native, dialect, expression, expected):
    put(native, "models/function_example.sql",
        "SELECT " + expression + " AS result FROM {{ ref('orders') }}")
    yaml = put(native, "models/function_example.yml", "version: 2\nmodels:\n  - name: function_example\n")
    project = Project(native, dialect=dialect)
    analysis = analyze(project, project.find("function_example"))
    assert analysis["reason"] is None, analysis
    column = next(item for item in analysis["columns"] if item["name"] == "result")
    assert column.get("inferred_type") == expected

    before = snapshot(native)
    changes, report = enrich(project, select=["function_example"])
    assert snapshot(native) == before
    assert not any(item.get("value") for item in report if item["property"] == "description")
    if expected is None:
        assert not changes.changed()
        assert any(item.get("reason") for item in report if item["property"] == "data_type")
    else:
        assert set(changes.changed()) == {yaml}
        assert any(item.get("value") == expected for item in report if item["property"] == "data_type")
        changes.apply()
        props = Project(native, dialect=dialect).find("function_example").columns["result"]
        assert props["data_type"] == expected
        assert not props.get("description")
        after = snapshot(native)
        assert after.keys() == before.keys()
        assert {path for path in before if before[path] != after[path]} == {"models/function_example.yml"}


@pytest.mark.parametrize("dialect", ["spark", "tsql"])
def test_function_enrichment_preserves_authored_metadata(native, dialect):
    put(native, "models/function_example.sql", "SELECT ABS(id) AS result FROM {{ ref('orders') }}")
    put(native, "models/function_example.yml", """version: 2
models:
  - name: function_example
    columns:
      - name: result
        data_type: decimal(20,0)
        description: Authored business meaning
""")
    before = snapshot(native)
    changes, _ = enrich(Project(native, dialect=dialect), select=["function_example"])
    assert not changes.changed()
    assert snapshot(native) == before


@pytest.mark.parametrize("dialect", SQL_DIALECTS)
def test_native_function_metadata_keeps_authored_names_and_lineage(native, dialect):
    put(native, "models/function_example.sql",
        "SELECT id AS order_id, ABS(id) AS magnitude FROM {{ ref('orders') }}")
    put(native, "models/function_example.yml", "version: 2\nmodels:\n  - name: function_example\n")
    project = Project(native, dialect=dialect)
    analysis = analyze(project, project.find("function_example"))
    assert analysis["reason"] is None, analysis
    assert [c["name"] for c in analysis["columns"]] == ["order_id", "magnitude"]
    expected_type = exp.DataType.build("BIGINT").sql(dialect=dialect)
    assert all(c["inferred_type"] == expected_type for c in analysis["columns"])
    assert all(c["upstream_columns"] == [{"resource_id": "model.shop.orders", "column": "id"}]
               for c in analysis["columns"])
    before = snapshot(native)
    changes, report = enrich(project, select=["function_example"])
    assert snapshot(native) == before
    assert {(r["column"], r["property"]) for r in report if "value" in r} == {
        ("order_id", "data_type"), ("order_id", "description"), ("magnitude", "data_type")}
    changes.apply()
    columns = Project(native, dialect=dialect).find("function_example").columns
    assert list(columns) == ["order_id", "magnitude"]
    assert columns["order_id"]["description"] == "Order identifier"
    assert not columns["magnitude"].get("description")


@pytest.mark.parametrize("alias,yaml_name", [("order_id", "ORDER_ID"), ('"OrderId"', "OrderId")])
def test_snowflake_identifier_normalization_does_not_duplicate_yaml(native, alias, yaml_name):
    put(native, "models/function_example.sql", "SELECT id AS " + alias + " FROM {{ ref('orders') }}")
    put(native, "models/function_example.yml",
        "version: 2\nmodels:\n  - name: function_example\n    columns:\n      - name: " + yaml_name + "\n")
    project = Project(native, dialect="snowflake")
    assert analyze(project, project.find("function_example"))["reason"] is None
    changes, _ = enrich(project, select=["function_example"])
    changes.apply()
    columns = Project(native, dialect="snowflake").find("function_example").columns
    assert list(columns) == [yaml_name]
    assert columns[yaml_name]["data_type"] == "BIGINT"
    assert columns[yaml_name]["description"] == "Order identifier"
