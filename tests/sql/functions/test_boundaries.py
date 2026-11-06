"""Shape and safety facts must not become implicit scalar/rewrite permissions."""

import pytest
from sqlglot import exp, parse_one

from dbt_extra.analysis.type_inference import inferred_types
from dbt_extra.sql.functions import CATALOG, FunctionShape, function_shape, function_spec, has_generators
from dbt_extra.sql.rewrites.structural import plain_queries
from dbt_extra.sql.parser import parse_authored
from dbt_extra.sql.safety import has_evaluation_barrier


@pytest.mark.parametrize("dialect,expression,expected", [
    ("spark", "json_tuple('{}', 'a')", FunctionShape("generator", 1, "one_per_row")),
    ("spark", "json_tuple('{}', 'a', 'b', 'c')", FunctionShape("generator", 3, "one_per_row")),
    ("spark", "inline_outer(array(named_struct('a', 1, 'b', 2)))", FunctionShape("generator", 2, "one_or_more")),
    ("spark", "inline_outer(items)", FunctionShape("generator", None, "one_or_more")),
    ("tsql", "string_split('a,b', ',')", FunctionShape("generator", 1, "zero_or_more")),
    ("tsql", "string_split('a,b', ',', 0)", FunctionShape("generator", 1, "zero_or_more")),
    ("tsql", "string_split('a,b', ',', 1)", FunctionShape("generator", 2, "zero_or_more")),
    ("tsql", "string_split('a,b', ',', flag)", FunctionShape("generator", None, "zero_or_more")),
    ("tsql", "string_split('a,b', ',', 2)", FunctionShape("generator", None, "zero_or_more")),
    ("spark", "mean(id)", FunctionShape("aggregate", 1, "one_per_group")),
    ("tsql", "isjson('{}')", FunctionShape("scalar", 1, "one_per_row")),
    ("databricks", "json_tuple('{}', 'a', 'b')", FunctionShape("generator", 2, "one_per_row")),
    ("databricks", "inline_outer(array(named_struct('a', 1, 'b', 2)))", FunctionShape("generator", 2, "one_or_more")),
    ("databricks", "inline_outer(items)", FunctionShape("generator", None, "one_or_more")),
    ("databricks", "inline_outer(array(named_struct('a', 1), named_struct('a', 1, 'b', 2)))", FunctionShape("generator", None, "one_or_more")),
    ("fabric", "string_split('a,b', ',')", FunctionShape("generator", 1, "zero_or_more")),
])
def test_explicit_output_arity_and_cardinality(dialect, expression, expected):
    node = parse_authored("SELECT " + expression, dialect).tree.selects[0]
    assert function_shape(node) == expected


@pytest.mark.parametrize("dialect,expression", [
    ("spark", "reflect('java.lang.Math', 'abs', -1)"),
    ("spark", "java_method('java.lang.Math', 'abs', -1)"),
    ("spark", "mystery_udf(id)"),
    ("tsql", "mystery_udf(id)"),
    ("tsql", "dbo.isjson('{}')"),
    ("spark", "app.isnull(id)"),
])
def test_dynamic_and_unknown_calls_never_gain_guessed_types(dialect, expression):
    tree = parse_authored("SELECT " + expression + " AS result FROM t", dialect).tree
    assert inferred_types(tree, {"t": {"id": "BIGINT"}}, dialect) == {}
    assert has_evaluation_barrier(tree)


@pytest.mark.parametrize("dialect,expression", [
    ("spark", "json_tuple('{}', 'a', 'b') AS (a, b)"),
    ("spark", "inline_outer(items) AS (a, b)"),
    ("spark", "explode(array(1, 2)) AS a"),
    ("spark", "posexplode(array(1, 2)) AS (pos, a)"),
    ("spark", "inline(array(named_struct('a', 1))) AS a"),
    ("tsql", "1 AS a FROM string_split('a,b', ',', 1) AS s"),
    ("duckdb", "unnest([1, 2]) AS a"),
    ("databricks", "json_tuple('{}', 'a', 'b') AS (a, b)"),
    ("databricks", "* FROM json_tuple('{}', 'a', 'b') AS j"),
    ("databricks", "inline_outer(items) AS (a, b)"),
    ("databricks", "* FROM inline_outer(array(named_struct('a', 1))) AS j"),
    ("fabric", "s.value FROM string_split('a,b', ',') AS s"),
])
def test_generators_cannot_supply_single_column_evidence_or_be_flattened(dialect, expression):
    tree = parse_authored("SELECT " + expression, dialect).tree
    assert has_generators(tree)
    assert not plain_queries(tree, aggregates=True)
    assert inferred_types(tree, {}, dialect) == {}


@pytest.mark.parametrize("dialect,expression", [
    ("spark", "explode(array(1, 2)) AS a"),
    ("spark", "inline_outer(array(named_struct('a', 1, 'b', 2))) AS (a, b)"),
    ("spark", "json_tuple('{}', 'a', 'b') AS (a, b)"),
    ("duckdb", "unnest([1, 2]) AS a"),
    ("tsql", "s.value FROM string_split('a,b', ',') AS s"),
    ("databricks", "* FROM json_tuple('{}', 'a', 'b') AS j"),
    ("databricks", "* FROM inline_outer(array(named_struct('a', 1))) AS j"),
    ("fabric", "s.value FROM string_split('a,b', ',') AS s"),
])
def test_generator_inspection_keeps_complete_query(native, dialect, expression):
    from dbt_extra.inspection import inspect
    from dbt_extra.project import Project
    from tests.helpers import put, snapshot

    put(native, "models/generator_example.sql", "SELECT " + expression)
    project = Project(native, dialect=dialect)
    before = snapshot(native)
    original, _, _ = inspect(project, "generator_example", optimized=False)
    optimized, _, issues = inspect(project, "generator_example")
    assert has_generators(optimized)
    # Qualification may add a projection alias, but does not invent generator
    # columns or change its arguments, output shape or evaluation count.
    assert [p.unalias().sql(dialect=dialect) for p in optimized.selects] == [p.unalias().sql(dialect=dialect) for p in original.selects]
    assert [n.sql(dialect=dialect) for n in optimized.find_all(exp.Anonymous, exp.UDTF)] == [
        n.sql(dialect=dialect) for n in original.find_all(exp.Anonymous, exp.UDTF)]
    assert not any("Simplification unavailable" in i["reason"] for i in issues)
    assert snapshot(native) == before


def test_catalogs_are_dialect_local_and_do_not_monkeypatch_sqlglot():
    assert len({name for catalog in CATALOG.values() for name in catalog}) >= 100
    for dialect in ("duckdb", "postgres", "snowflake", "bigquery", "fabric", "redshift", "trino", "athena"):
        node = parse_authored("SELECT json_tuple('{}', 'a')", dialect).tree.selects[0]
        assert function_spec(node) is None
    raw = parse_one("SELECT isjson('{}')", read="tsql").selects[0]
    assert isinstance(raw, exp.Anonymous)
    assert function_spec(raw) is None
    assert function_spec(parse_authored("SELECT isjson('{}')", "tsql").tree.selects[0]) is not None
    assert function_spec(raw) is None


def test_redshift_empty_exclude_is_not_a_semantic_clause():
    tree = parse_authored("SELECT t.id FROM t", "redshift").tree
    assert tree.args["exclude"] == []
    assert plain_queries(tree)
    tree.set("exclude", [exp.to_identifier("id")])
    assert not plain_queries(tree)
