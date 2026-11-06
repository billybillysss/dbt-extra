"""Dialect-specific set-returning functions must not masquerade as scalar values."""

import pytest
from sqlglot import exp, parse_one

from dbt_extra.analysis.type_inference import inferred_types
from dbt_extra.sql.rewrites.engine import optimize_source
from dbt_extra.sql.functions import FunctionShape, function_shape, has_generators
from dbt_extra.sql.rewrites.structural import deduplicate_subqueries, plain_queries
from dbt_extra.sql.parser import parse_authored


@pytest.mark.parametrize("dialect,expression,columns,rows", [
    ("postgres", "jsonb_each('{}'::jsonb)", 2, "zero_or_more"),
    ("postgres", "jsonb_path_query('{}'::jsonb,'$.a')", 1, "zero_or_more"),
    ("databricks", "variant_explode(parse_json('[1,2]'))", 3, "zero_or_more"),
    ("databricks", "variant_explode_outer(parse_json('[1,2]'))", 3, "one_or_more"),
    ("databricks", "window(TIMESTAMP '2026-01-01','1 minute')", 1, "zero_or_more"),
    ("databricks", "session_window(TIMESTAMP '2026-01-01','1 minute')", 1, "unknown"),
    ("snowflake", "result_scan(last_query_id())", None, "unknown"),
])
@pytest.mark.parametrize("table_form", [False, True])
def test_registered_generator_shapes_and_rewrite_barriers(dialect, expression, columns, rows, table_form):
    code = f"SELECT * FROM {expression} AS g" if table_form else f"SELECT {expression} AS result"
    tree = parse_authored(code, dialect).tree
    call = next(n for n in tree.find_all(exp.Anonymous) if n.name.lower() == expression.split('(')[0])
    assert function_shape(call) == FunctionShape("generator", columns, rows)
    assert has_generators(tree)
    assert inferred_types(tree, {}, dialect) == {}
    assert not plain_queries(tree, aggregates=True)
    assert deduplicate_subqueries(tree.copy()) == tree
    after = parse_authored(optimize_source(code, dialect), dialect).tree
    assert has_generators(after)
    assert [n.name.lower() for n in tree.find_all(exp.Anonymous)] == [n.name.lower() for n in after.find_all(exp.Anonymous)]


@pytest.mark.parametrize("dialect", ["postgres", "postgres, normalization_strategy=case_sensitive"])
def test_native_generate_series_is_set_returning_in_postgresql_only(dialect):
    expression = "generate_series(1,3)"
    tree = parse_authored(f"SELECT {expression} AS result, 1 AS constant", dialect).tree
    assert isinstance(tree.selects[0].this, exp.ExplodingGenerateSeries)
    assert has_generators(tree) and has_generators(parse_one(expression, read=dialect), dialect)
    assert inferred_types(tree, {}, dialect) == {}
    assert not plain_queries(tree, aggregates=True)
    scalar = parse_authored(f"SELECT {expression} AS result", "duckdb").tree
    assert not has_generators(scalar)
    assert inferred_types(scalar, {}, "duckdb") == {"result": "INT[]"}
