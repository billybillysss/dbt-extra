"""Evaluation-sensitive native calls and narrow local output-removal proofs."""

import duckdb
import pytest
from sqlglot import exp, parse_one

from dbt_extra.inspection import inspect
from dbt_extra.sql.rewrites.engine import optimize_source
from dbt_extra.project import Project
from dbt_extra.sql.rewrites.structural import deduplicate_subqueries
from dbt_extra.sql.parser import parse_authored
from dbt_extra.sql.safety import discardable, function_properties, movable
from dbt_extra.sql.safety import has_evaluation_barrier
from tests.helpers import put


@pytest.mark.parametrize("dialect,expression,effect", [
    *(('snowflake', f'seq{width}()', 'volatile') for width in (1, 2, 4, 8)),
    ("snowflake", "current_warehouse()", "statement_stable"),
    ("trino", "current_timezone()", "statement_stable"),
    ("databricks", "current_catalog()", "statement_stable"),
    ("spark", "randstr(4)", "volatile"),
    ("spark", "shuffle(array(1,2,3))", "volatile"),
    ("databricks", "shuffle(array(1,2,3))", "volatile"),
    ("databricks", "uniform(0,1)", "volatile"),
    ("trino", "shuffle(ARRAY[1,2,3])", "volatile"),
    ("athena", "shuffle(ARRAY[1,2,3])", "volatile"),
    ("databricks", "secret('scope','key')", "unknown"),
    ("databricks", "ai_classify('hello',array('a','b'))", "unknown"),
    ("duckdb", "levenshtein('abc','abd')", "unknown"),
])
def test_native_effects_block_factoring_and_model_expansion(native, dialect, expression, effect):
    node = parse_one(expression, read=dialect)
    assert not isinstance(node, exp.Anonymous)
    assert function_properties(node, dialect).volatility == effect
    code = f"SELECT a.v AS av, b.v AS bv FROM (SELECT {expression} AS v FROM t) a CROSS JOIN (SELECT {expression} AS v FROM t) b"
    tree = parse_authored(code, dialect).tree
    assert has_evaluation_barrier(tree)
    assert deduplicate_subqueries(tree.copy()) == tree
    optimized = parse_authored(optimize_source(code, dialect, schema={"t": {"id": "BIGINT"}}), dialect).tree
    assert not optimized.find(exp.With)
    assert len(list(optimized.find_all(type(node)))) == 2
    put(native, "models/effect_upstream.sql", f"SELECT {expression} AS v FROM t")
    put(native, "models/effect_downstream.sql", "SELECT v FROM {{ ref('effect_upstream') }}")
    expanded, _, _ = inspect(Project(native, dialect=dialect), "effect_downstream", compiled=False)
    assert not expanded.find(type(node)), "Effect-sensitive upstream model must not be inlined"


def test_function_properties_honor_explicit_dialect_without_changing_metadata():
    raw = parse_one("isjson('{}')", read="tsql")
    assert not function_properties(raw).known
    assert function_properties(raw, "tsql, version=16").known
    node = parse_authored("SELECT xact_state()", "tsql").tree.selects[0]
    assert function_properties(node).known
    assert not function_properties(node, "fabric").known
    assert node.meta["extra_function_dialect"] == "tsql"
    generator = parse_one("inline_outer(items)", read="databricks")
    properties = function_properties(generator, "databricks")
    assert properties.kind == "generator" and properties.columns is None


@pytest.mark.parametrize("expression", ["a AND b", "a OR b", "NOT a"])
def test_boolean_connectives_do_not_create_unknown_function_barriers(expression):
    tree = parse_authored("SELECT " + expression + " AS result FROM t", "duckdb").tree
    assert not has_evaluation_barrier(tree)
    for node in tree.find_all(exp.Func):
        assert function_properties(node, "duckdb").volatility == "immutable"


@pytest.mark.parametrize("dialect", ["spark", "databricks", "spark, normalization_strategy=case_sensitive"])
@pytest.mark.parametrize("name", ["isnull", "isnotnull"])
@pytest.mark.parametrize("argument", ["id", "NULL", "1", "isnull(id)"])
@pytest.mark.parametrize("mode", ["source", "inspection"])
def test_unused_null_checks_are_pruned_without_function_movement(native, dialect, name, argument, mode):
    expression = f"{name}({argument})"
    node = parse_authored("SELECT " + expression, dialect).tree.selects[0]
    assert discardable(node, dialect) and not movable(node)
    assert has_evaluation_barrier(node), "Output removal must not grant general movement permission"
    code = f"SELECT q.id FROM (SELECT id, {expression} AS unused FROM t) q"
    if mode == "source":
        candidate = optimize_source(code, dialect, schema={"t": {"id": "BIGINT"}})
    else:
        put(native, "models/null_check.sql", code)
        candidate = inspect(Project(native, dialect=dialect), "null_check", compiled=False)[0].sql(dialect=dialect)
    tree = parse_authored(candidate, dialect).tree
    assert not tree.find(exp.Anonymous)
    if mode == "source":
        assert optimize_source(candidate, dialect, schema={"t": {"id": "BIGINT"}}) == candidate
    # Run the equivalent native null predicates offline, not Spark functions or
    # arbitrary UDFs. Verify output labels, types, multiplicities and NULL rows.
    reference = parse_one(code, read=dialect)
    for call in reversed(list(reference.find_all(exp.Anonymous))):
        check = exp.Is(this=call.expressions[0].copy(), expression=exp.Null())
        call.replace(exp.Not(this=check) if call.name.lower() == "isnotnull" else check)
    with duckdb.connect() as con:
        con.execute("CREATE TABLE t(id BIGINT)")
        for rows in ([], [(None,), (1,), (1,), (2,)]):
            if rows:
                con.executemany("INSERT INTO t VALUES (?)", rows)
            before = con.execute(reference.sql(dialect="duckdb"))
            expected = before.description, before.fetchall()
            after = con.execute(tree.sql(dialect="duckdb"))
            assert (after.description, after.fetchall()) == expected


@pytest.mark.parametrize("dialect", ["spark", "databricks"])
@pytest.mark.parametrize("expression", [
    "isnull(CAST(id AS INT))", "isnotnull(id + 1)", "isnull(rand())",
    "isnotnull(mystery(id))", "app.isnull(id)", "isnull(id, 0)",
    "isnotnull(json_array_length('bad'))", "isnull(id) /* retain */", "`isnull`(id)",
])
def test_null_check_removal_does_not_erase_argument_effects_or_comments(dialect, expression):
    node = parse_authored("SELECT " + expression, dialect).tree.selects[0]
    assert not discardable(node, dialect)
    code = f"SELECT q.id FROM (SELECT id, {expression} AS risky FROM t) q"
    candidate = parse_authored(optimize_source(code, dialect, schema={"t": {"id": "BIGINT"}}), dialect).tree
    assert any(p.output_name == "risky" for s in candidate.find_all(exp.Select) for p in s.selects)


@pytest.mark.parametrize("clause", ["ORDER BY unused", "GROUP BY id, unused", "ORDER BY 2"])
def test_null_check_output_dependencies_remain_live(clause):
    code = f"SELECT q.id FROM (SELECT id, isnull(id) AS unused FROM t {clause}) q"
    tree = parse_authored(optimize_source(code, "spark", schema={"t": {"id": "BIGINT"}}), "spark").tree
    assert tree.find(exp.Anonymous)


@pytest.mark.parametrize("dialect", ["spark", "databricks"])
@pytest.mark.parametrize("mode", ["source", "inspection"])
def test_live_null_check_alias_is_not_duplicated_or_replaced(native, dialect, mode):
    code = "SELECT isnotnull(id) AS z, z AS y FROM t"
    if mode == "source":
        tree = parse_authored(optimize_source(code, dialect, schema={"t": {"id": "BIGINT"}}), dialect).tree
    else:
        put(native, "models/null_alias.sql", code)
        tree = inspect(Project(native, dialect=dialect), "null_alias", compiled=False)[0]
    assert len(list(tree.find_all(exp.Anonymous))) == 1
    assert isinstance(tree.selects[0].unalias(), exp.Anonymous)
    assert isinstance(tree.selects[1].unalias(), exp.Column)
    assert tree.selects[1].unalias().name == "z"
