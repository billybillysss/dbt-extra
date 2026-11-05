"""Shared SQL safety and scope primitives do not require a workbook."""

import pytest

from dbt_extra import SpecError
from dbt_extra.sql import UnsupportedSQL, parse_authored, render
from dbt_extra.sql.parser import read_query
from dbt_extra.sql.scopes import query_scopes, relation_tables, rewrite_scopes, scope_at


@pytest.mark.parametrize("code", [
    "SELECT 1; SELECT 2", "DELETE FROM orders", "CREATE TABLE x AS SELECT 1",
    "SELECT 1 INTO x", "SELECT 1 UNION SELECT 1, 2", "SELECT * FROM {{ ref('orders') }}",
])
def test_static_parser_rejects_non_readonly_or_unmasked_sql(code):
    with pytest.raises(SpecError):
        read_query(code, "test", "duckdb")


@pytest.mark.parametrize("code", [
    "SELECT {{ opaque_macro() }} AS id", "SELECT * FROM {{ ref(var('model')) }}",
    "{% if execute %}SELECT 1{% endif %}",
    "WITH RECURSIVE x AS (SELECT 1 AS id UNION ALL SELECT id + 1 FROM x) SELECT * FROM x",
])
def test_opaque_or_dynamic_templates_are_explicitly_unavailable(code):
    with pytest.raises(UnsupportedSQL):
        parse_authored(code, "duckdb")


def test_scope_paths_distinguish_shadowed_ctes():
    parsed = parse_authored("WITH x AS (SELECT id FROM orders), y AS (WITH x AS (SELECT id FROM customers) SELECT id FROM x) SELECT id FROM x", "duckdb")
    scopes = query_scopes(parsed.tree)
    named = [(name, path) for name, path, _ in scopes if name == "x"]
    assert len(named) == 2
    assert named[0][1] != named[1][1]
    assert all(scope_at(parsed.tree, path) is node for _, path, node in scopes)
    assert {table.name for table in relation_tables(parsed.tree)} == {"orders", "customers"}


def test_scoped_expression_edit_preserves_alias_and_dbt_reference():
    code = "{{ config(materialized='view') }}\nWITH base AS (SELECT id + 0 AS id FROM {{ ref('orders') }}) SELECT id FROM base"
    parsed = parse_authored(code, "duckdb")
    _, path, _ = query_scopes(parsed.tree)[0]
    rewrite_scopes(parsed, [{"path": path, "projection": 0, "column": "id", "changes": {"expression": "id + 1"}}], "duckdb", "test")
    candidate = render(parsed.tree, parsed, "duckdb", prefix=True)
    assert "id + 1 AS id" in candidate
    assert "{{ ref('orders') }}" in candidate
    assert candidate.startswith("{{ config(materialized='view') }}")
    assert parse_authored(candidate, "duckdb").tree == parsed.tree
