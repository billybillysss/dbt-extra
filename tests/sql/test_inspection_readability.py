"""Display aliases and identity cleanup must not weaken SQL safety guards."""

from collections import Counter

import duckdb
import pytest
from sqlglot import exp, parse_one

from dbt_extra.inspection import inspect
from dbt_extra.sql import parse_authored, render
from dbt_extra.sql.aliases import ALIAS_TARGET, available_alias, readable_name
from dbt_extra.sql.rewrites.query_boundaries import simplify_query_boundaries
from tests.helpers import SQL_DIALECTS, project, put, snapshot


@pytest.mark.parametrize("name, expected", [
    ("stg_orders", "orders"), ("brz_orders", "orders"),
    ("slv_orders", "orders"), ("gld_orders", "orders"),
    ("raw_orders", "raw_orders"), ("orders_stg", "orders_stg"),
    ("stg", "stg"), ("stg-orders", "stg_orders"), ("stage_orders", "stage_orders"),
    ("Customer_Revenue", "customer_revenue"),
    ("gld_finance_customer_lifetime_revenue_summary", "finance_cust_lifetime_rev_sum"),
])
def test_alias_names_use_only_recognized_prefixes_and_fixed_abbreviations(name, expected):
    assert readable_name(name) == expected


def test_long_aliases_keep_leading_words_and_stable_hashes():
    name = "gld_international_customer_transaction_account_revenue_summary"
    alias = readable_name(name)
    assert alias.startswith("international_")
    assert len(alias) <= ALIAS_TARGET
    assert alias == readable_name(name)
    assert alias != readable_name(name + "_daily")
    assert "customer_revenue" != alias
    assert len(readable_name("x" * 100)) <= ALIAS_TARGET


def test_alias_collisions_use_context_then_case_insensitive_numeric_suffixes():
    assert available_alias("orders", {"Orders"}, context="shop") == "shop_orders"
    assert available_alias("orders", {"Orders", "SHOP_ORDERS"}, context="shop") == "shop_orders_2"
    assert available_alias("orders", {"Orders", "orders_2"}) == "orders_3"


@pytest.mark.parametrize("dialect", SQL_DIALECTS)
@pytest.mark.parametrize("reference, context", [("ref('stg_orders')", None),
                                                ("ref('pkg', 'stg_orders')", "pkg"),
                                                ("source('shop', 'orders')", "shop")])
def test_generated_aliases_preserve_authored_aliases_and_correlated_bindings(dialect, reference, context):
    parsed = parse_authored("select id from {{ " + reference + " }}", dialect)
    token = next(iter(parsed.refs))
    # Reserve a mixed-case authored alias. The inner source must not capture its
    # enclosing reference, nor may the renderer rename the authored alias.
    tree = parse_one(f'''SELECT "Orders".id FROM base AS "Orders"
        WHERE EXISTS (SELECT {token}.id FROM {token}
                      WHERE {token}.id = "Orders".id)''', read="duckdb")
    code = render(tree, parsed, dialect)
    reparsed = parse_authored(code, dialect).tree
    expected = f"{context}_stg_orders" if context == "pkg" else "shop_orders" if context else "orders_2"
    assert any(t.alias == "Orders" for t in reparsed.find_all(exp.Table))
    assert any(t.alias == expected for t in reparsed.find_all(exp.Table))
    assert sum(c.table == "Orders" for c in reparsed.find_all(exp.Column)) == 2
    assert sum(c.table == expected for c in reparsed.find_all(exp.Column)) == 2
    assert token not in code and "extra_input_" not in code


@pytest.mark.parametrize("authored", ["a", "b", "c", "buyer", "seller", "CustomerPurchaseHistory"])
def test_authored_aliases_are_not_shortened_or_reassigned(authored):
    parsed = parse_authored(f"select {authored}.id from {{{{ ref('stg_orders') }}}} as {authored}", "duckdb")
    assert f"{authored}.id" in render(parsed.tree, parsed, "duckdb")


def test_expanded_long_alias_retains_original_name_in_comment():
    name = "gld_international_customer_transaction_account_revenue_summary"
    parsed = parse_authored("select id from {{ ref('" + name + "') }}", "duckdb")
    token = next(iter(parsed.refs))
    tree = parse_one(f"SELECT {token}.id FROM (SELECT t.id FROM raw_input AS t) AS {token}")
    code = render(tree, parsed, "duckdb")
    assert f"Expanded from: {name}" in code
    assert readable_name(name) in code
    assert token not in code
    assert code == render(tree, parsed, "duckdb")


@pytest.mark.parametrize("sql", [
    "SELECT q.id AS renamed FROM (SELECT t.id AS id FROM t WHERE t.id > 1) AS q",
    "SELECT q.total AS renamed FROM (SELECT SUM(t.amount) AS total FROM t GROUP BY t.id) AS q",
    "SELECT q.id AS renamed FROM (SELECT CAST(t.id AS BIGINT) AS id FROM t) AS q",
    "WITH q AS (SELECT SUM(t.amount) AS total FROM t GROUP BY t.id) SELECT q.total AS renamed FROM q",
])
@pytest.mark.parametrize("rows", [[], [(1, 2), (1, 3), (2, 0), (None, 4)]])
def test_identity_cleanup_preserves_rows_nulls_and_aggregate_grain(sql, rows):
    tree = parse_one(sql, read="duckdb")
    cleaned = simplify_query_boundaries(tree.copy(), "duckdb")
    assert len(list(cleaned.find_all(exp.Subquery))) < len(list(tree.find_all(exp.Subquery))) or tree.args.get("with_")
    assert not cleaned.find(exp.CTE)
    assert cleaned.named_selects == tree.named_selects
    assert simplify_query_boundaries(cleaned.copy(), "duckdb") == cleaned
    with duckdb.connect() as con:
        con.execute("CREATE TABLE t (id BIGINT, amount BIGINT)")
        if rows:
            con.executemany("INSERT INTO t VALUES (?, ?)", rows)
        assert Counter(con.execute(sql).fetchall()) == Counter(con.execute(cleaned.sql(dialect="duckdb")).fetchall())


@pytest.mark.parametrize("sql", [
    "SELECT q.id FROM (SELECT t.id FROM t LIMIT 1) AS q",
    "SELECT q.id FROM (SELECT DISTINCT t.id FROM t) AS q",
    "SELECT q.id FROM (SELECT t.id FROM t ORDER BY t.id) AS q",
    "SELECT q.id FROM (SELECT t.id FROM t) AS q WHERE q.id > 1",
    "SELECT q.id, q.id AS repeated FROM (SELECT RANDOM() AS id) AS q",
    "SELECT q.id FROM (SELECT t.id, CAST(t.amount AS INT) AS unused FROM t) AS q",
    "SELECT q.id FROM (SELECT 1 AS id, COUNT(*) AS n FROM t) AS q",
    "SELECT q.id FROM (SELECT t.id AS id, COUNT(*) AS n FROM t GROUP BY 1) AS q",
    "SELECT q.id FROM (SELECT t.id AS id FROM t GROUP BY id) AS q",
    "WITH q AS MATERIALIZED (SELECT t.id FROM t) SELECT q.id FROM q",
    "WITH q AS (SELECT RANDOM() AS id) SELECT q.id FROM q",
    "WITH q AS (SELECT t.id FROM t) SELECT a.id FROM q AS a JOIN q AS b ON a.id = b.id",
])
def test_cleanup_retains_unproven_evaluation_and_binding_boundaries(sql):
    tree = parse_one(sql, read="duckdb")
    assert simplify_query_boundaries(tree.copy(), "duckdb") == tree


def test_cleanup_preserves_fallible_evaluation(native):
    put(native, "models/unsafe.sql", "select cast('bad' as int) as value")
    put(native, "models/target.sql", "select value as result from {{ ref('unsafe') }}")
    p = project(native)
    before = snapshot(native)
    full, original, _ = inspect(p, "target", ["result"], optimized=False)
    cleaned, parsed, _ = inspect(p, "target", ["result"])
    with duckdb.connect() as con:
        for tree, source in [(full, original), (cleaned, parsed)]:
            with pytest.raises(duckdb.ConversionException):
                con.execute(render(tree, source, "duckdb"))
    assert snapshot(native) == before
