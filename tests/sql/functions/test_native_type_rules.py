"""Return-type correctness, including schemas, overloads and real DuckDB binding."""

import duckdb
import pytest
from sqlglot import Dialect, exp, parse_one
from sqlglot.optimizer.annotate_types import annotate_types
from sqlglot.optimizer.qualify_columns import qualify_columns

from dbt_extra.analysis.type_inference import inferred_types
from dbt_extra.sql.functions import FunctionSpec
from dbt_extra.sql.parser import parse_authored
from tests.sql.functions.helpers import enrichment


CASES = [
    ("postgres", "array_position(ARRAY[1,2],2)", "INTEGER"),
    ("duckdb", "array_position([1,2],2)", "INTEGER"),
    ("spark", "array_position(array(1,2),2)", "BIGINT"),
    ("databricks", "array_position(array(1,2),2)", "BIGINT"),
    ("trino", "array_position(ARRAY[1,2],2)", "BIGINT"),
    ("athena", "array_position(ARRAY[1,2],2)", "BIGINT"),
    ("redshift", "json_parse('{}')", "SUPER"),
    ("databricks", "parse_json('{}')", "VARIANT"),
    ("snowflake", "to_number('1.2',10,2)", "DECIMAL(10,2)"),
    ("snowflake", "to_number('1')", "DECIMAL(38,0)"),
    ("postgres", "sum(CAST(1 AS BIGINT))", "NUMERIC"),
    ("postgres", "sum(CAST(1 AS INT))", "BIGINT"),
    ("postgres", "avg(CAST(1 AS BIGINT))", "NUMERIC"),
    ("postgres", "avg(CAST(1 AS DECIMAL(12,2)))", "NUMERIC"),
    ("postgres", "stddev(CAST(1 AS BIGINT))", "NUMERIC"),
    ("postgres", "var_pop(CAST(1 AS BIGINT))", "NUMERIC"),
    ("duckdb", "sum(CAST(1 AS BIGINT))", "HUGEINT"),
    ("duckdb", "sum(CAST(1 AS INT))", "HUGEINT"),
    ("duckdb", "sum(CAST(1 AS DECIMAL(12,2)))", "DECIMAL(38,2)"),
    ("duckdb", "avg(CAST(1 AS DECIMAL(12,2)))", "DOUBLE"),
    ("tsql", "sum(CAST(1 AS INT))", "INT"),
    ("fabric", "sum(CAST(1 AS INT))", "INT"),
    ("tsql", "avg(CAST(1 AS BIGINT))", "BIGINT"),
    ("fabric", "avg(CAST(1 AS INT))", "INT"),
    ("tsql", "sum(CAST(1 AS DECIMAL(12,2)))", "DECIMAL(38,2)"),
    ("fabric", "avg(CAST(1 AS DECIMAL(12,2)))", "DECIMAL(38,6)"),
    ("redshift", "sum(CAST(1 AS BIGINT))", "BIGINT"),
    ("redshift", "avg(CAST(1 AS BIGINT))", "BIGINT"),
    ("redshift", "avg(CAST(1 AS DECIMAL(12,2)))", "DECIMAL(38,2)"),
    ("spark", "sum(CAST(1 AS DECIMAL(12,2)))", "DECIMAL(22,2)"),
    ("spark", "avg(CAST(1 AS DECIMAL(12,2)))", "DECIMAL(16,6)"),
    ("databricks", "sum(CAST(1 AS DECIMAL(12,2)))", "DECIMAL(22,2)"),
    ("databricks", "avg(CAST(1 AS DECIMAL(12,2)))", "DECIMAL(16,6)"),
    ("trino", "approx_percentile(CAST(1 AS BIGINT),0.5)", "BIGINT"),
    ("trino", "approx_percentile(CAST(1 AS DOUBLE),ARRAY[0.25,0.5])", "ARRAY(DOUBLE)"),
    ("duckdb", "strpos('abc','b')", "BIGINT"),
    ("duckdb", "sign(CAST(1 AS BIGINT))", "TINYINT"),
    ("duckdb", "round(CAST(1 AS BIGINT),0)", "BIGINT"),
    ("duckdb", "to_timestamp(1.0)", "TIMESTAMPTZ"),
    ("duckdb", "get_current_time()", "TIMETZ"),
    ("duckdb", "weekofyear(DATE '2026-01-01')", "BIGINT"),
    ("duckdb", "repeat(CAST('a' AS BLOB),2)", "BLOB"),
    ("duckdb", "json_extract_string('{}',0)", "VARCHAR"),
    ("duckdb", "json_extract_path_text('{}',['$.a','$.b'])", "VARCHAR[]"),
    ("duckdb", "approx_quantile(CAST(1 AS BIGINT),0.5)", "BIGINT"),
    ("duckdb", "approx_quantile(CAST(1 AS BIGINT),[0.25,0.5])", "BIGINT[]"),
]


@pytest.mark.parametrize("dialect,expression,returns", CASES)
def test_native_types_are_per_call_and_do_not_replace_nodes(dialect, expression, returns):
    tree = parse_authored(f"SELECT {expression} AS result", dialect).tree
    before = tree.dump()
    metadata = dict(Dialect.get_or_raise(dialect).EXPRESSION_METADATA)
    baseline = annotate_types(tree.copy(), dialect=dialect).dump()
    expected = exp.DataType.build(returns, dialect=dialect).sql(dialect=dialect)
    for settings in (dialect, dialect + ", normalization_strategy=case_sensitive"):
        assert inferred_types(tree, {}, settings) == {"result": expected}
        scoped = parse_authored(f"SELECT q.result FROM (SELECT {expression} AS result) q", settings).tree
        assert inferred_types(scoped, {}, settings) == {"result": expected}
    assert tree.dump() == before
    assert type(tree.selects[0].this) is type(parse_one(expression, read=dialect))
    assert Dialect.get_or_raise(dialect).EXPRESSION_METADATA == metadata
    assert annotate_types(tree.copy(), dialect=dialect).dump() == baseline


@pytest.mark.parametrize("dialect,expression,returns", CASES)
def test_native_type_repairs_enrich_missing_yaml_only(native, dialect, expression, returns):
    enrichment(native, dialect, FunctionSpec("native_example", expression, returns, 0, 0))


@pytest.mark.parametrize("dialect,expected", [
    ("duckdb", "DECIMAL(38, 2)"), ("postgres", "DECIMAL"),
    ("tsql", "NUMERIC(38, 2)"), ("fabric", "DECIMAL(38, 2)"),
    ("redshift", "DECIMAL(38, 2)"), ("spark", "DECIMAL(22, 2)"),
    ("databricks", "DECIMAL(22, 2)"),
])
@pytest.mark.parametrize("modifier", ["", "DISTINCT "])
def test_aggregate_types_use_declared_schema_in_qualified_scopes(dialect, expected, modifier):
    schema = {"t": {"d": "DECIMAL(12,2)"}}
    tree = parse_authored(f"SELECT SUM({modifier}t.d) AS result FROM t", dialect).tree
    tree = qualify_columns(tree, schema=schema, dialect=dialect)
    assert list(inferred_types(tree, schema, dialect).values()) == [expected]


@pytest.mark.parametrize("dialect,expression", [
    ("spark", "sum(mystery(1))"), ("duckdb", "avg(mystery(1))"),
    ("databricks", "sum(CAST(1 AS DECIMAL(35,2)))"),
    ("duckdb", "round(CAST(1 AS DECIMAL(12,2)),0)"),
    ("duckdb", "approx_quantile(CAST(1 AS DECIMAL(12,2)),0.5)"),
    ("snowflake", "to_number('1',mystery(1),0)"),
    ("snowflake", "to_number('1',0,2)"),
    ("trino", "approx_percentile(CAST(1 AS INT),0.5)"),
    ("trino", "approx_percentile(mystery(1),0.5)"),
    ("trino", "approx_percentile(CAST(1 AS BIGINT),mystery(1))"),
    ("duckdb", "json_extract_string('{}',mystery(1))"),
])
def test_uncertified_numeric_overloads_do_not_inherit_an_incorrect_type(dialect, expression):
    assert inferred_types(parse_authored(f"SELECT {expression} AS result", dialect).tree, {}, dialect) == {}


@pytest.mark.parametrize("expression", [expression for dialect, expression, _ in CASES if dialect == "duckdb"])
def test_duckdb_types_match_the_offline_binder_without_evaluating_functions(expression):
    tree = parse_authored(f"SELECT {expression} AS result", "duckdb").tree
    inferred = inferred_types(tree, {}, "duckdb")["result"]
    with duckdb.connect(":memory:") as con:
        actual = con.execute("DESCRIBE SELECT " + expression + " AS result").fetchone()[1]
    assert exp.DataType.build(actual, dialect="duckdb") == exp.DataType.build(inferred, dialect="duckdb")
