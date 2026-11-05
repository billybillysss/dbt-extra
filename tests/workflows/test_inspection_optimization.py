"""Inspection removes redundant work without changing selected-row multiplicity."""

from collections import Counter

import duckdb
import pytest
from sqlglot import exp

from dbt_extra.inspection import inspect
from dbt_extra.sql import parse_authored, render
from tests.helpers import SQL_DIALECTS, invoke, project, put, snapshot


@pytest.fixture
def customer_project(native):
    put(native, "models/schema.yml", """version: 2
sources:
  - name: raw
    tables:
      - name: orders
      - name: customers
      - name: payments
""")
    put(native, "models/order_payments.sql", """
select order_id, sum(amount) as total_amount
from {{ source('raw', 'payments') }}
group by order_id
""")
    put(native, "models/customer_orders.sql", """
with order_payments as (select * from {{ ref('order_payments') }})
select cast(o.user_id as bigint) as customer_id,
       count(*) as number_of_orders, sum(p.total_amount) as total_amount
from {{ source('raw', 'orders') }} as o
left join order_payments as p on o.id = p.order_id
group by cast(o.user_id as bigint)
""")
    put(native, "models/gld_customers.sql", """
with customer_orders as (select * from {{ ref('customer_orders') }})
select c.id as customer_id, trim(c.first_name) as first_name,
       o.number_of_orders, o.total_amount
from {{ source('raw', 'customers') }} as c
left join customer_orders as o on c.id = o.customer_id
""")
    return native


@pytest.mark.parametrize("dialect", SQL_DIALECTS)
def test_selected_customer_inspection_removes_unused_joins(customer_project, dialect):
    p = project(customer_project)
    p.dialect = dialect
    before = snapshot(customer_project)
    tree, parsed, issues = inspect(p, "gld_customers", ["first_name"], compiled=False)
    code = render(tree, parsed, dialect)
    assert not any("Simplification unavailable" in issue["reason"] for issue in issues)
    assert not list(tree.find_all(exp.Join))
    assert not list(tree.find_all(exp.Subquery))
    assert not list(tree.find_all(exp.CTE))
    assert len(list(tree.find_all(exp.Select))) == 1
    assert [p.output_name for p in tree.selects] == ["first_name"]
    assert "TRIM(" in code
    assert "{{ source('raw', 'customers') }}" in code
    assert "{{ ref(" not in code
    assert "{{ source('raw', 'orders') }}" not in code
    assert "{{ source('raw', 'payments') }}" not in code
    parse_authored(code, dialect)
    assert snapshot(customer_project) == before


@pytest.mark.parametrize("flags", [(), ("--optimize", "true", "--expand", "true", "--compile", "true")])
def test_inspect_cli_defaults_expand_and_optimize(customer_project, flags):
    before = snapshot(customer_project)
    result = invoke(customer_project, "inspect", "gld_customers", "--columns", "first_name", *flags)
    assert result.exit_code == 0, result.output
    assert "raw.customers" in result.output
    assert "TRIM(" in result.output
    assert "JOIN" not in result.output
    assert "extra_selected_output" not in result.output
    assert "{{ ref(" not in result.output
    assert snapshot(customer_project) == before


def test_inspect_cli_can_disable_optimization_and_expansion(customer_project):
    unoptimized = invoke(customer_project, "inspect", "gld_customers", "--columns", "first_name", "--optimize", "false", "--compile", "false")
    assert unoptimized.exit_code == 0, unoptimized.output
    assert unoptimized.output.upper().count("LEFT JOIN") == 2
    assert "extra_selected_output" in unoptimized.output
    assert "{{ source('raw', 'payments') }}" in unoptimized.output
    unexpanded = invoke(customer_project, "inspect", "gld_customers", "--columns", "first_name", "--expand", "false", "--compile", "false")
    assert unexpanded.exit_code == 0, unexpanded.output
    assert "{{ ref('customer_orders') }}" in unexpanded.output
    assert "LEFT JOIN" in unexpanded.output


@pytest.mark.parametrize("empty", [False, True])
def test_customer_join_elimination_preserves_rows(customer_project, empty):
    p = project(customer_project)
    full, full_parsed, _ = inspect(p, "gld_customers", optimized=False, compiled=False)
    selected, parsed, _ = inspect(p, "gld_customers", ["first_name"], compiled=False)

    def executable(tree, parsed):
        code = render(tree, parsed, "duckdb")
        for table in ("customers", "orders", "payments"):
            code = code.replace("{{ source('raw', '" + table + "') }}", "input_" + table)
        return code

    with duckdb.connect() as con:
        con.execute("create table input_customers (id bigint, first_name varchar)")
        con.execute("create table input_orders (id bigint, user_id bigint)")
        con.execute("create table input_payments (order_id bigint, amount bigint)")
        if not empty:
            con.execute("insert into input_customers values (1, ' Ada '), (1, ' Ada '), (2, 'Bob'), (3, NULL), (NULL, 'Ada')")
            con.execute("insert into input_orders values (10, 1), (11, 1), (12, 2), (13, NULL)")
            con.execute("insert into input_payments values (10, 2), (10, 3), (12, 4), (NULL, 5)")
        expected = Counter((row[1],) for row in con.execute(executable(full, full_parsed)).fetchall())
        assert Counter(con.execute(executable(selected, parsed)).fetchall()) == expected


@pytest.mark.parametrize("join, rhs, where, column", [
    ("left", "select id, amount from {{ ref('orders') }}", "", "id"),
    ("inner", "select id, sum(amount) as amount from {{ ref('orders') }} group by id", "", "id"),
    ("left", "select id, sum(amount) as amount from {{ ref('orders') }} group by id", "where b.amount > 1", "id"),
    ("left", "select id, sum(amount) as amount from {{ ref('orders') }} group by id", "", "amount"),
    ("left", "select id, amount from {{ ref('orders') }} group by id, amount", "", "id"),
])
@pytest.mark.parametrize("rows", [[], [(1, 2), (1, 3), (2, 0), (3, -1), (None, 4)]])
def test_inspection_retains_required_joins(native, join, rhs, where, column, rows):
    put(native, "models/target.sql", """
select a.id as id, b.amount as amount
from {{ ref('orders') }} as a
""" + join + " join (" + rhs + ") as b on a.id = b.id " + where)
    p = project(native)
    full, full_parsed, _ = inspect(p, "target", optimized=False, compiled=False)
    selected, parsed, issues = inspect(p, "target", [column], compiled=False)
    assert not any("Simplification unavailable" in issue["reason"] for issue in issues)
    assert list(selected.find_all(exp.Join))
    with duckdb.connect() as con:
        con.execute("create table input_orders (id bigint, amount bigint)")
        if rows:
            con.executemany("insert into input_orders values (?, ?)", rows)
        full_sql = render(full, full_parsed, "duckdb").replace("{{ source('raw', 'orders') }}", "input_orders")
        selected_sql = render(selected, parsed, "duckdb").replace("{{ source('raw', 'orders') }}", "input_orders")
        index = [p.output_name for p in full.selects].index(column)
        expected = Counter((row[index],) for row in con.execute(full_sql).fetchall())
        assert Counter(con.execute(selected_sql).fetchall()) == expected
