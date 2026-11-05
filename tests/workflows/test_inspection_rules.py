"""Extra inspection rules must preserve bags, barriers, and dbt boundaries."""

from collections import Counter
from itertools import product

import duckdb
import pytest
from sqlglot import exp, parse_one

from dbt_extra.inspection import inspect, plan
from dbt_extra.sql import parse_authored, render
from dbt_extra.sql.inspection_rules import (deduplicate_subqueries, normalize_predicates,
                                       optimize_safe_joins, pushdown_safe_predicates)
from tests.helpers import SQL_DIALECTS, project, put, snapshot


CASES = {
    "normalize": "select id from INPUT where (id = 1 and amount = 10) or id = 2",
    "pushdown": "select q.id from (select distinct id from INPUT) q where q.id = 2",
    "join": "select a.id, b.amount, c.amount as other from INPUT a cross join INPUT b "
            "join INPUT c on a.id = c.id and b.id = c.id",
    "deduplicate": "select a.id, a.n, b.n as other from "
                   "(select id, count(*) as n from INPUT group by id) a join "
                   "(select id, count(*) as n from INPUT group by id) b on a.id = b.id",
    "limit": "select q.id from (select id from INPUT order by id limit 1) q where q.id = 2",
    "offset": "select q.id from (select id from INPUT order by id offset 2) q where q.id = 2",
    "global": "select q.id from (select 7 as id, count(*) as n from INPUT) q where q.id = 8",
    "count": "select q.id from (select count(*) as id from INPUT) q where q.id = 0",
    "or_join": "select a.id, b.id as b_id, c.id as c_id from INPUT a cross join INPUT b "
               "join INPUT c on a.id = c.id or b.id = c.id",
    "left": "select a.id, q.id as other from INPUT a left join "
            "(select distinct id from INPUT) q on a.id = q.id where q.id is null",
    "right": "select a.id, b.amount from INPUT a right join INPUT b on a.id = b.id "
             "where a.id = 2",
    "full": "select a.id, b.amount from INPUT a full join INPUT b on a.id = b.id "
            "where a.id is null",
    "window": "select q.id, q.rn from "
              "(select id, row_number() over(order by id, amount) as rn from INPUT) q where q.rn = 1",
    "qualify": "select id, row_number() over(order by id, amount) as rn from INPUT qualify rn = 1",
    "distinct_on": "select q.id, q.amount from "
                   "(select distinct on(id) id, amount from INPUT order by id, amount) q where q.amount = 20",
    "union": "select q.id from (select id from INPUT union select id from INPUT) q where q.id = 2",
    "union_all": "select q.id from (select id from INPUT union all select id from INPUT) q where q.id = 2",
    "having": "select q.id from "
              "(select id, count(*) as n from INPUT group by id having count(*) > 1) q where q.id = 2",
    "exists": "select a.id from INPUT a where exists(select 1 from INPUT b where a.id = b.id)",
    "not_in": "select id from INPUT where id not in(select id from INPUT)",
    "scalar_empty": "select id, (select amount from INPUT where id = 999) as scalar from INPUT",
    "scalar_many": "select id, (select amount from INPUT where id = 2) as scalar from INPUT",
    "limited_duplicates": "select a.id, b.id as other from "
                          "(select id from INPUT order by id limit 1) a cross join "
                          "(select id from INPUT order by id limit 1) b",
    "materialized": "with q as materialized (select distinct id from INPUT) "
                    "select id from q where id = 2",
    "shadowed": "with q as (select id from INPUT where id = 1) "
                "select a.id, b.id as other from (select id, count(*) as n from q group by id) a "
                "cross join (with q as (select id from INPUT where id = 2) "
                "select id, count(*) as n from q group by id) b",
}


def target(native, case):
    put(native, "models/schema.yml", "version: 2\nsources:\n  - name: raw\n    tables:\n      - name: orders\n")
    put(native, "models/target.sql", CASES[case].replace("INPUT", "{{ source('raw', 'orders') }}"))
    return project(native)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("columns", [None, ["id"]])
def test_extra_inspection_rules_preserve_results(native, case, empty, columns):
    p = target(native, case)
    before = snapshot(native)
    original, original_parsed, _ = inspect(p, "target", optimized=False)
    optimized, parsed, issues = inspect(p, "target", columns)
    assert not any("Simplification unavailable" in issue["reason"] for issue in issues)
    with duckdb.connect() as con:
        con.execute("create schema raw; create table raw.orders(id bigint, amount bigint)")
        if not empty:
            con.execute("insert into raw.orders values (1, 10), (2, 20), (2, 20), (2, 40), (3, NULL), (NULL, 30)")

        def result(tree, parsed):
            try:
                return Counter(con.execute(render(tree, parsed, "duckdb")).fetchall())
            except duckdb.Error as exc:
                return type(exc)

        expected = result(original, original_parsed)
        if case == "scalar_many" and not empty:
            assert expected is duckdb.InvalidInputException
        else:
            assert isinstance(expected, Counter), expected
        if columns and isinstance(expected, Counter):
            index = [projection.output_name for projection in original.selects].index("id")
            projected = Counter()
            for row, count in expected.items():
                projected[(row[index],)] += count
            expected = projected
        elif columns:
            # The warehouse can itself prune an unselected scalar expression.
            baseline, baseline_parsed, _ = inspect(p, "target", columns, optimized=False)
            expected = result(baseline, baseline_parsed)
            assert isinstance(expected, Counter)
        assert result(optimized, parsed) == expected
    assert snapshot(native) == before


@pytest.mark.parametrize("case", ["normalize", "pushdown", "join", "deduplicate"])
@pytest.mark.parametrize("dialect", SQL_DIALECTS)
@pytest.mark.parametrize("compiled", [False, True])
def test_extra_rules_simplify_and_roundtrip(native, case, dialect, compiled):
    p = target(native, case)
    p.dialect = dialect
    before = snapshot(native)
    tree, parsed, issues = inspect(p, "target", compiled=compiled)
    assert not any("Simplification unavailable" in issue["reason"] for issue in issues)
    if case == "normalize":
        assert isinstance(tree.args["where"].this, exp.And)
    elif case == "pushdown":
        assert tree.args.get("where") is None
        assert any(select.args.get("where") for select in list(tree.find_all(exp.Select))[1:])
    elif case == "join":
        assert len(list(tree.find_all(exp.Join))) == 2
        assert not any(join.kind == "CROSS" for join in tree.find_all(exp.Join))
    else:
        assert len(list(tree.find_all(exp.CTE))) == 1
        assert len(list(tree.find_all(exp.Select))) == 2
        assert len(list(tree.find_all(exp.Table))) == 3
    code = render(tree, parsed, dialect)
    parse_authored(code, dialect)
    assert ("{{ source(" in code) is not compiled
    assert "extra_ref_" not in code
    assert "raw" in plan(tree, parsed, dialect)
    assert snapshot(native) == before


@pytest.mark.parametrize("case", ["normalize", "pushdown", "join", "deduplicate"])
def test_optimization_false_keeps_original_structure(native, case):
    p = target(native, case)
    tree, _, _ = inspect(p, "target", optimized=False)
    if case == "normalize":
        assert isinstance(tree.args["where"].this, exp.Or)
    elif case == "pushdown":
        assert tree.args.get("where") is not None
        assert not next(tree.find_all(exp.Subquery)).this.args.get("where")
    elif case == "join":
        assert any(join.kind == "CROSS" for join in tree.find_all(exp.Join))
    else:
        assert len(list(tree.find_all(exp.Subquery))) == 2
        assert not list(tree.find_all(exp.CTE))


@pytest.mark.parametrize("case", ["limit", "offset", "global", "window", "qualify", "distinct_on", "union", "having", "materialized"])
def test_predicate_guard_keeps_barriers(case):
    tree = parse_one(CASES[case].replace("INPUT", "orders"), read="duckdb")
    before = tree.copy()
    assert pushdown_safe_predicates(tree, dialect="duckdb") == before


@pytest.mark.parametrize("case", ["or_join", "left", "right", "full"])
def test_join_guard_keeps_unsupported_joins(case):
    tree = parse_one(CASES[case].replace("INPUT", "orders"), read="duckdb")
    before = tree.copy()
    assert optimize_safe_joins(tree) == before


@pytest.mark.parametrize("sql", [
    "select a.id from (select id from t limit 1) a cross join (select id from t limit 1) b",
    "select a.id from (select id from t offset 1) a cross join (select id from t offset 1) b",
    "with q as materialized (select id from t) select a.id from (select distinct id from q) a cross join (select distinct id from q) b",
    "select a.id from (select distinct random() as id from t) a cross join (select distinct random() as id from t) b",
    "select a.id from (select first(id) as id from t) a cross join (select first(id) as id from t) b",
    "select a.id from (select id from t tablesample reservoir(1 rows)) a cross join (select id from t tablesample reservoir(1 rows)) b",
])
def test_deduplication_keeps_unstable_or_scoped_queries(sql):
    tree = parse_one(sql, read="duckdb")
    before = tree.copy()
    assert deduplicate_subqueries(tree) == before


def test_deduplication_keeps_stored_self_owners():
    tree = parse_one("select a.id from (select id, count(*) as n from t group by id) a "
                     "join (select id, count(*) as n from t group by id) b on a.id = b.id")
    for owner, table in enumerate(tree.find_all(exp.Table)):
        table.meta["extra_owner"] = f"model.shop.owner_{owner}"
    before = tree.copy()
    assert deduplicate_subqueries(tree) == before
    assert [table.meta for table in tree.find_all(exp.Table)] == [table.meta for table in before.find_all(exp.Table)]


def test_boolean_normalization_preserves_three_valued_logic():
    with duckdb.connect() as con:
        con.execute("create table truth_values(a boolean, b boolean, c boolean)")
        con.executemany("insert into truth_values values (?, ?, ?)", list(product((True, False, None), repeat=3)))
        for predicate in ["(a and b) or c", "(a or b) and (c or a)", "not ((a and b) or c)", "a or (b and c)"]:
            tree = parse_one("select " + predicate + " as value from truth_values")
            optimized = normalize_predicates(tree.copy())
            assert con.execute(tree.sql()).fetchall() == con.execute(optimized.sql()).fetchall()


def test_boolean_normalization_is_bounded():
    predicate = " or ".join(f"(a{i} and b{i})" for i in range(12))
    tree = parse_one("select id from t where " + predicate)
    before = tree.copy()
    assert normalize_predicates(tree) == before
