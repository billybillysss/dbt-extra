"""Physical inspection names come from source definitions or resolved dbt evidence."""

from collections import Counter
import json

import duckdb
import pytest
from sqlglot import exp, parse_one

from dbt_extra.errors import SpecError
from dbt_extra.inspection import inspect, plan
from dbt_extra.sql import render
from tests.helpers import invoke, project, put, snapshot


def source_yaml(native, settings="schema: main_raw", table_settings="identifier: raw_orders"):
    put(native, "models/schema.yml", "version: 2\nsources:\n  - name: raw\n    "
        + settings.replace("\n", "\n    ") + "\n    tables:\n      - name: orders\n        "
        + table_settings.replace("\n", "\n        ") + "\n")


def manifest(native, *, source=None, models=None):
    nodes = {}
    for name, fields in (models or {}).items():
        relative = {"orders": "models/slv/orders.sql", "revenue": "models/gld/revenue.sql"}.get(name, f"models/{name}.sql")
        nodes[f"model.shop.{name}"] = {"name": name, "resource_type": "model", "package_name": "shop",
            "original_file_path": relative, "raw_code": (native / relative).read_text(), **fields,
            "config": {"materialized": "view" if name == "orders" else "table", **fields.get("config", {})}}
    put(native, "target/manifest.json", json.dumps({"metadata": {"project_name": "shop", "adapter_type": "duckdb"},
        "nodes": nodes, "sources": {"source.shop.raw.orders": {"name": "orders", "resource_type": "source",
            "package_name": "shop", "source_name": "raw", **source}} if source is not None else {}}))


@pytest.mark.parametrize("dialect", ["duckdb", "postgres", "snowflake", "bigquery", "spark", "tsql"])
def test_literal_source_compiles_actual_schema_and_identifier(native, dialect):
    source_yaml(native)
    p = project(native)
    p.dialect = dialect
    before = snapshot(native)
    tree, parsed, issues = inspect(p, "revenue", ["revenue"])
    table, = tree.find_all(exp.Table)
    assert (table.catalog, table.db, table.name) == ("", "main_raw", "raw_orders")
    code = render(tree, parsed, dialect)
    assert "{{" not in code and "extra_ref_" not in code
    assert not any("Physical relation unavailable" in i["reason"] for i in issues)
    parse_one(code, read=dialect)
    assert "main_raw" in plan(tree, parsed, dialect)
    assert snapshot(native) == before


@pytest.mark.parametrize("flags, compiled", [((), True), (("--compile", "true"), True), (("--compile", "false"), False)])
def test_cli_compilation_default_and_explicit_flags(native, flags, compiled):
    source_yaml(native)
    result = invoke(native, "inspect", "revenue", *flags)
    assert result.exit_code == 0, result.output
    assert ("main_raw.raw_orders" in result.output) is compiled
    assert ("{{ source('raw', 'orders') }}" in result.output) is not compiled


def test_compilation_settings_and_cli_precedence(native):
    source_yaml(native)
    put(native, "extra_project.yaml", "version: 2\ninspection: {compile: false}\n")
    assert "{{ source(" in invoke(native, "inspect", "revenue").output
    assert "main_raw.raw_orders" in invoke(native, "inspect", "revenue", "--compile", "true").output
    put(native, "extra_project.yaml", "version: 2\ninspection: {compile: 'true'}\n")
    with pytest.raises(SpecError, match="inspection.compile: expected a boolean"):
        project(native)


@pytest.mark.parametrize("settings, table_settings, expected", [
    ("database: landing\nschema: actual", "identifier: actual_orders", ("landing", "actual", "actual_orders")),
    ("database: landing", "description: Default names", ("landing", "raw", "orders")),
    ("database: landing\nschema: group_schema", "schema: table_schema\nidentifier: actual_orders", ("landing", "table_schema", "actual_orders")),
    ("schema: 'schema.with.dot'", "identifier: 'orders.with.dot'", ("", "schema.with.dot", "orders.with.dot")),
])
def test_source_name_components_are_not_logical_names(native, settings, table_settings, expected):
    source_yaml(native, settings, table_settings)
    tree, parsed, _ = inspect(project(native), "orders", optimized=False)
    table, = tree.find_all(exp.Table)
    assert (table.catalog, table.db, table.name) == expected
    reparsed = parse_one(render(tree, parsed, "duckdb"), read="duckdb")
    actual, = reparsed.find_all(exp.Table)
    assert (actual.catalog, actual.db, actual.name) == expected


@pytest.mark.parametrize("dialect", ["duckdb", "postgres", "snowflake", "bigquery", "spark", "tsql"])
def test_source_quoting_is_inherited_and_table_can_override(native, dialect):
    source_yaml(native, "database: Landing\nschema: 'Actual Schema'\nquoting: {database: true, schema: true, identifier: false}",
                "identifier: 'Order Data'\nquoting: {identifier: true}")
    p = project(native)
    p.dialect = dialect
    tree, parsed, _ = inspect(p, "orders")
    table, = tree.find_all(exp.Table)
    assert all(table.args[k].args["quoted"] for k in ("catalog", "db", "this"))
    parse_one(render(tree, parsed, dialect), read=dialect)


@pytest.mark.parametrize("component", ["schema", "database", "identifier"])
def test_dynamic_source_names_need_manifest(native, component):
    settings = "schema: main_raw"
    table_settings = "identifier: raw_orders"
    if component == "identifier":
        table_settings = "identifier: '{{ var(\"table\") }}'"
    elif component == "schema":
        settings = "schema: '{{ target.schema }}'"
    else:
        settings += "\ndatabase: '{{ target.database }}'"
    source_yaml(native, settings, table_settings)
    before = snapshot(native)
    tree, parsed, issues = inspect(project(native), "orders")
    assert "{{ source(" in render(tree, parsed, "duckdb")
    assert any("Physical relation unavailable" in i["reason"] for i in issues)
    assert snapshot(native) == before
    values = {"database": "warehouse", "schema": "main_raw", "identifier": "raw_orders"}
    values[component] = "resolved_name"
    manifest(native, source={**values, "relation_name": '.'.join('"' + values[k] + '"' for k in ("database", "schema", "identifier"))})
    tree, parsed, issues = inspect(project(native), "orders")
    table, = tree.find_all(exp.Table)
    assert (table.catalog, table.db, table.name) == tuple(values[k] for k in ("database", "schema", "identifier"))
    assert "{{" not in render(tree, parsed, "duckdb")
    assert not any("Physical relation unavailable" in i["reason"] for i in issues)


def test_literal_source_names_override_conflicting_manifest(native):
    source_yaml(native)
    manifest(native, source={"schema": "old_schema", "identifier": "old_orders", "relation_name": '"old_schema"."old_orders"'})
    tree, _, _ = inspect(project(native), "orders")
    table, = tree.find_all(exp.Table)
    assert (table.db, table.name) == ("main_raw", "raw_orders")


def test_authored_source_quoting_overrides_old_manifest_policy(native):
    source_yaml(native, "schema: main_raw\nquoting: {schema: false, identifier: false}")
    manifest(native, source={"schema": "main_raw", "identifier": "raw_orders", "relation_name": '"main_raw"."raw_orders"'})
    tree, _, _ = inspect(project(native), "orders")
    table, = tree.find_all(exp.Table)
    assert not table.this.args["quoted"]
    assert not table.args["db"].args["quoted"]


@pytest.mark.parametrize("options", [{"expanded": False}, {"boundaries": ["orders"]}])
@pytest.mark.parametrize("relation_name", [True, False])
def test_unexpanded_model_uses_resolved_manifest_not_custom_schema(native, options, relation_name):
    fields = {"database": "warehouse", "schema": "target_custom", "alias": "actual_orders", "config": {"schema": "custom"}}
    if relation_name:
        fields["relation_name"] = '"warehouse"."target_custom"."actual_orders"'
    put(native, "dbt_project.yml", "name: shop\nmodels:\n  shop:\n    +schema: custom\n")
    manifest(native, models={"orders": fields})
    tree, parsed, _ = inspect(project(native), "revenue", **options)
    table, = tree.find_all(exp.Table)
    assert (table.catalog, table.db, table.name) == ("warehouse", "target_custom", "actual_orders")
    assert "{{ ref(" not in render(tree, parsed, "duckdb")


@pytest.mark.parametrize("change", ["code", "config", "ephemeral"])
def test_invalid_model_relation_evidence_is_not_guessed(native, change):
    if change == "ephemeral":
        put(native, "models/slv/orders.sql", "{{ config(materialized='ephemeral') }}\nselect 1 as id, 2 as amount")
    manifest(native, models={"orders": {"relation_name": "production.actual_orders"}})
    if change == "code":
        put(native, "models/slv/orders.sql", "select 1 as id, 2 as amount")
    elif change == "config":
        put(native, "dbt_project.yml", "name: shop\nmodels:\n  shop:\n    +schema: changed\n")
    tree, parsed, issues = inspect(project(native), "revenue", expanded=False)
    assert "{{ ref('orders') }}" in render(tree, parsed, "duckdb")
    assert any("Physical relation unavailable" in i["reason"] for i in issues)


@pytest.mark.parametrize("raw", ["production.orders; other.table", "production.orders alias", "read_csv('secret')", "{{ target.schema }}.orders"])
def test_malformed_manifest_relation_is_not_treated_as_a_table(native, raw):
    manifest(native, models={"orders": {"relation_name": raw}})
    tree, parsed, issues = inspect(project(native), "revenue", expanded=False)
    assert "{{ ref('orders') }}" in render(tree, parsed, "duckdb")
    assert any("Physical relation unavailable" in i["reason"] for i in issues)


def test_this_uses_owning_model_even_in_expanded_upstream(native):
    put(native, "models/slv/orders.sql", "select id, amount from {{ this }}")
    manifest(native, models={"orders": {"relation_name": '"history"."stored_orders"'},
                             "revenue": {"relation_name": '"analytics"."stored_revenue"'}})
    tree, parsed, _ = inspect(project(native), "revenue")
    table, = tree.find_all(exp.Table)
    assert (table.db, table.name) == ("history", "stored_orders")
    assert "{{ this }}" not in render(tree, parsed, "duckdb")


def test_unknown_relations_warn_and_false_skips_resolution(native):
    put(native, "models/target.sql", "select id from {{ ref('missing') }}")
    tree, parsed, issues = inspect(project(native), "target")
    assert "{{ ref('missing') }}" in render(tree, parsed, "duckdb")
    assert any("Physical relation unavailable" in i["reason"] for i in issues)
    _, _, issues = inspect(project(native), "target", compiled=False)
    assert not any("Physical relation unavailable" in i["reason"] for i in issues)


@pytest.mark.parametrize("kind", ["model", "seed", "snapshot"])
def test_package_and_versioned_boundary_refs_compile_from_manifest(native, kind):
    put(native, "models/target.sql", "select id from {{ ref('dependency', 'facts', version=2) }}")
    node = {"name": "facts", "resource_type": kind, "package_name": "dependency", "version": 2,
            "original_file_path": "models/facts.sql", "relation_name": '"shared"."facts_v2"'}
    put(native, "target/manifest.json", json.dumps({"metadata": {"project_name": "shop"},
        "nodes": {f"{kind}.dependency.facts.v2": node}}))
    tree, parsed, _ = inspect(project(native), "target")
    table, = tree.find_all(exp.Table)
    assert (table.db, table.name) == ("shared", "facts_v2")
    assert "{{" not in render(tree, parsed, "duckdb")


def test_compiled_sql_preserves_rows_and_aliases(native):
    source_yaml(native)
    before = snapshot(native)
    full, full_parsed, _ = inspect(project(native), "revenue", optimized=False)
    tree, parsed, _ = inspect(project(native), "revenue", ["revenue"])
    with duckdb.connect() as con:
        con.execute("create schema main_raw")
        con.execute("create table main_raw.raw_orders(id int, amount int)")
        con.execute("insert into main_raw.raw_orders values (1, 2), (1, 2), (2, -1), (3, 10), (4, NULL)")
        expected = Counter((row[1],) for row in con.execute(render(full, full_parsed, "duckdb")).fetchall())
        assert Counter(con.execute(render(tree, parsed, "duckdb")).fetchall()) == expected
    assert snapshot(native) == before
