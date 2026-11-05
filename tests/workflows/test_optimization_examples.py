"""The teaching inputs must demonstrate real rules, not merely successful formatting."""

from collections import Counter
from pathlib import Path
import shutil

import duckdb
import pytest
from sqlglot import exp

from dbt_extra.inspection import inspect
from dbt_extra.optimization import optimize
from dbt_extra.project import Project
from dbt_extra.sql import parse_authored, render
from dbt_extra.sql.macros import macro_calls, parse_model
from dbt_extra.sql.references import resolve_ref
from tests.helpers import invoke, optimizer_inputs, snapshot


EXAMPLE = Path(__file__).resolve().parents[2] / "examples/jaffle_shop"
FOLDER = "models/gld/optimization"
SELECT = f"path:{FOLDER}/**"
NAMES = sorted(path.stem for path in (EXAMPLE / FOLDER).glob("*.sql"))
ORDERED = {"gld_customer_order_ranking", "gld_customer_leaderboard"}


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("source_examples") / "jaffle_shop"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("target", "logs", "extra_review", "dbt_packages"))
    optimizer_inputs(root)
    return Project(root)


@pytest.fixture(scope="module")
def source_changes(demo):
    return optimize(demo, select=[SELECT])


def test_source_examples_really_rewrite_and_preserve_interfaces(demo, source_changes):
    changes, skipped = source_changes
    assert not skipped
    assert len(changes.optimization_report) == len(NAMES) == 14
    for name in NAMES:
        model = demo.find(name)
        if model.id in skipped:
            assert model.path not in changes.after
            continue
        candidate = changes.after[model.path].decode("utf-8")
        assert changes.optimization_report[model.id]["status"] == "rewritten", name
        before = parse_model(demo, model.code, expand=True)
        after = parse_model(demo, candidate, expand=True)
        assert before.prefix == after.prefix
        assert before.config == after.config
        assert Counter(raw for _, _, raw, _ in macro_calls(candidate)) == Counter(
            raw for _, _, raw, _ in macro_calls(model.code))
        if name != "gld_optimizer_schema_projection":
            assert [p.output_name for p in before.tree.selects] == [p.output_name for p in after.tree.selects]
        if name == "gld_optimizer_constants":
            assert "3 AS sample_value" in candidate
        elif name == "gld_optimizer_projections":
            assert len(list(after.tree.find_all(exp.Select))) == 1
            assert not list(after.tree.find_all(exp.CTE))
            assert "unused_status" not in candidate
            assert "TRUE" not in candidate
            assert "o.customer_id > 0" in candidate
        elif name == "gld_optimizer_schema_projection":
            assert [p.output_name for p in after.tree.selects] == ["order_id", "customer_id", "order_date", "status"]
            assert not list(after.tree.find_all(exp.Star))
            assert next(after.tree.find_all(exp.Table)).alias == "a"
            assert all(isinstance(p, exp.Column) for p in after.tree.selects)
        elif name in {"gld_customer_lifetime_value", "gld_customer_leaderboard"}:
            assert changes.optimization_report[model.id]["status"] == "rewritten"
            assert "unused_status" not in candidate
            assert "largest_order" not in candidate
            assert "returned_order_count" not in candidate
            expected = parse_model(demo, model.code).tree.copy()
            for query in expected.find_all(exp.Select):
                query.set("expressions", [p for p in query.selects if p.output_name not in {
                    "unused_status", "largest_order", "returned_order_count"}])
            assert parse_model(demo, candidate).tree == expected
            if name == "gld_customer_leaderboard":
                assert any(s.args.get("distinct") for s in after.tree.find_all(exp.Select))
                assert list(after.tree.find_all(exp.Having))
                assert list(after.tree.find_all(exp.Window))
                assert after.tree.args.get("limit")
        elif name == "gld_optimizer_predicates":
            assert after.tree.args.get("where") is None
            inner = next(after.tree.find_all(exp.Subquery)).this
            assert inner.args.get("distinct") and inner.args.get("where")
            assert "TRUE" not in candidate
        elif name == "gld_optimizer_boolean_normalization":
            assert isinstance(after.tree.args["where"].this, exp.And)
        elif name == "gld_optimizer_join_simplification":
            assert len(list(after.tree.find_all(exp.Join))) == 2
            assert not any(j.kind == "CROSS" for j in after.tree.find_all(exp.Join))
        elif name == "gld_optimizer_shared_subqueries":
            assert len(list(after.tree.find_all(exp.CTE))) == 1
            assert len(list(after.tree.find_all(exp.Select))) == 2
        elif name == "gld_optimizer_customer_profile":
            assert not list(after.tree.find_all(exp.CTE))
            assert "unused_first_order" not in candidate
        elif name == "gld_customer_order_ranking":
            assert "unused_status" not in candidate
            assert len(list(after.tree.find_all(exp.Window))) == 1
            assert after.tree.args.get("limit")
        elif name == "gld_distinct_paying_customers":
            assert "unused_status" not in candidate
            distinct = next(s for s in after.tree.find_all(exp.Select) if s.args.get("distinct"))
            assert [p.output_name for p in distinct.selects] == ["customer_id", "order_id"]
        elif name == "gld_payment_union":
            assert not list(after.tree.find_all(exp.Union))
            assert len(list(after.tree.find_all(exp.Table))) == 1
            assert isinstance(after.tree.args["where"].this, exp.Or)
        elif name == "gld_high_value_customers":
            assert not list(after.tree.find_all(exp.Exists))
            assert len(list(after.tree.find_all(exp.In))) == 1
            assert len(list(after.tree.find_all(exp.Avg))) == 2


@pytest.mark.parametrize("case", ["projections", "predicates", "boolean_normalization", "join_simplification", "shared_subqueries"])
def test_focused_inspection_shapes(demo, case):
    name = "gld_optimizer_" + case
    before, _, _ = inspect(demo, name, expanded=False, optimized=False, compiled=False)
    tree, parsed, issues = inspect(demo, name, expanded=False, compiled=False)
    assert not any("unavailable" in issue["reason"].lower() for issue in issues)
    assert tree != before
    assert [p.output_name for p in tree.selects] == [p.output_name for p in before.selects]
    if case == "projections":
        assert len(list(tree.find_all(exp.Select))) == 1
        assert not list(tree.find_all(exp.CTE))
        assert "unused_status" not in render(tree, parsed, "duckdb")
    elif case == "predicates":
        assert before.args.get("where") is not None
        assert tree.args.get("where") is None
        inner = next(tree.find_all(exp.Subquery)).this
        assert inner.args.get("distinct")
        assert inner.args.get("where") is not None
        assert "TRUE" not in render(tree, parsed, "duckdb")
    elif case == "boolean_normalization":
        assert isinstance(before.args["where"].this, exp.Or)
        assert isinstance(tree.args["where"].this, exp.And)
    elif case == "join_simplification":
        assert any(join.kind == "CROSS" for join in before.find_all(exp.Join))
        assert len(list(tree.find_all(exp.Join))) == 2
        assert not any(join.kind == "CROSS" for join in tree.find_all(exp.Join))
    else:
        assert not list(before.find_all(exp.CTE))
        assert len(list(tree.find_all(exp.CTE))) == 1
        assert len(list(tree.find_all(exp.Select))) == 2
        assert len(list(tree.find_all(exp.Join))) == 1
    parse_authored(render(tree, parsed, "duckdb"), "duckdb")


def test_selected_profile_needs_expansion_to_prove_join_elimination(demo):
    name = "gld_optimizer_customer_profile"
    full, _, _ = inspect(demo, name, ["first_name"], optimized=False, compiled=False)
    tree, parsed, issues = inspect(demo, name, ["first_name"], compiled=False)
    assert list(full.find_all(exp.Join))
    assert not any("unavailable" in issue["reason"].lower() for issue in issues)
    assert not list(tree.find_all(exp.Join))
    assert len(list(tree.find_all(exp.Select))) == 1
    code = render(tree, parsed, "duckdb")
    assert "{{ source('jaffle_shop', 'customers') }}" in code
    assert "TRIM(" in code
    unexpanded, boundary, _ = inspect(demo, name, ["first_name"], expanded=False, compiled=False)
    assert "{{ ref('gld_customers') }}" in render(unexpanded, boundary, "duckdb")


@pytest.fixture(params=[False, True], ids=["duplicates-and-nulls", "empty"])
def warehouse(demo, request):
    """Materialize only reachable authored dependencies in an in-memory test database."""
    with duckdb.connect() as con:
        con.execute("create table input_raw_customers(id bigint, first_name varchar, last_name varchar)")
        con.execute("create table input_raw_orders(id bigint, user_id bigint, order_date date, status varchar)")
        con.execute("create table input_raw_payments(id bigint, order_id bigint, payment_method varchar, amount bigint)")
        if not request.param:
            con.execute("insert into input_raw_customers values (1,' Ada ','A'),(1,' Ada ','A'),"
                        "(2,'Bob','B'),(3,NULL,'C'),(4,'No orders','D'),(NULL,'Null key',NULL)")
            con.execute("insert into input_raw_orders values "
                        "(10,1,'2020-01-01','completed'),(10,1,'2020-01-01','completed'),"
                        "(11,1,'2020-01-02','completed'),(12,1,'2020-01-03','completed'),"
                        "(20,2,'2020-01-01','completed'),(21,2,'2020-01-02','completed'),"
                        "(22,2,'2020-01-03','returned'),(30,3,'2020-01-01',NULL),"
                        "(31,3,'2020-01-02','completed'),(32,3,'2020-01-03','completed'),"
                        "(40,11,'2020-01-01','completed'),(50,NULL,NULL,'completed')")
            con.execute("insert into input_raw_payments values "
                        "(1,10,'credit_card',1000),(1,10,'credit_card',1000),"
                        "(2,11,'bank_transfer',2000),(3,12,'credit_card',1000),"
                        "(4,20,'credit_card',3000),(5,21,'coupon',2000),"
                        "(6,22,'credit_card',-100),(7,30,NULL,0),"
                        "(8,40,'credit_card',NULL),(9,NULL,'credit_card',500),"
                        "(10,31,'credit_card',1000),(11,32,'bank_transfer',1000)")
        built = set()

        def executable(tree, parsed):
            # Unexpanded inspection preserves scalar Jinja; expand it for execution only.
            value = parse_model(demo, render(tree, parsed, "duckdb"), expand=True)
            tree = value.tree.copy()
            for table in tree.find_all(exp.Table):
                ref = value.refs.get(table.name)
                if ref is None:
                    continue  # CTE, not a dbt reference
                if ref.kind == "source":
                    target = "input_raw_" + ref.args[-1]
                else:
                    upstream = resolve_ref(demo, ref)
                    assert upstream is not None
                    target = "input_" + upstream.name
                    if upstream.kind == "model" and target not in built:
                        model = parse_model(demo, upstream.code, expand=True)
                        sql = executable(model.tree, model)
                        con.execute(f'create table "{target}" as {sql}')
                        built.add(target)
                table.set("this", exp.to_identifier(target))
                table.set("db", None)
                table.set("catalog", None)
            return tree.sql(dialect="duckdb")

        def result(tree, parsed, ordered=False):
            cursor = con.execute(executable(tree, parsed))
            names = [column[0] for column in cursor.description]
            types = [str(column[1]) for column in cursor.description]
            rows = cursor.fetchall()
            return names, types, rows if ordered else Counter(rows)

        yield result


@pytest.mark.parametrize("name", NAMES)
def test_authored_demo_rewrites_preserve_results(demo, source_changes, warehouse, name):
    model = demo.find(name)
    before = parse_model(demo, model.code, expand=True)
    changes, skipped = source_changes
    if model.id in skipped:
        assert model.path not in changes.after
        return
    after = parse_model(demo, changes.after[model.path].decode("utf-8"), expand=True)
    assert warehouse(before.tree, before, name in ORDERED) == warehouse(after.tree, after, name in ORDERED)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("expanded", [False, True], ids=["isolated", "expanded"])
def test_inspected_demo_rewrites_preserve_results(demo, warehouse, name, expanded):
    before = parse_model(demo, demo.find(name).code, expand=True)
    tree, parsed, issues = inspect(demo, name, expanded=expanded, compiled=False)
    assert not any("Simplification unavailable" in issue["reason"] for issue in issues)
    assert warehouse(before.tree, before, name in ORDERED) == warehouse(tree, parsed, name in ORDERED)


def test_selected_profile_preserves_customer_multiplicity(demo, warehouse):
    name = "gld_optimizer_customer_profile"
    before = parse_model(demo, demo.find(name).code, expand=True)
    names, types, full = warehouse(before.tree, before)
    expected = Counter()
    index = names.index("first_name")
    for row, count in full.items():
        expected[(row[index],)] += count
    tree, parsed, _ = inspect(demo, name, ["first_name"], compiled=False)
    assert warehouse(tree, parsed) == (["first_name"], [types[index]], expected)


@pytest.mark.parametrize("name,column", [
    ("gld_customer_lifetime_value", "lifetime_value"),
    ("gld_customer_leaderboard", "ranked_revenue"),
])
def test_macro_models_have_structural_selected_output_inspection(demo, warehouse, name, column):
    before = parse_model(demo, demo.find(name).code, expand=True)
    names, types, rows = warehouse(before.tree, before)
    expected = Counter()
    index = names.index(column)
    values = rows.items() if isinstance(rows, Counter) else ((row, 1) for row in rows)
    for row, count in values:
        expected[(row[index],)] += count
    complete, _, _ = inspect(demo, name, [column], optimized=False, compiled=False)
    tree, parsed, issues = inspect(demo, name, [column], compiled=False)
    assert not any("unavailable" in issue["reason"].lower() for issue in issues)
    assert len(list(tree.find_all(exp.Select))) < len(list(complete.find_all(exp.Select)))
    code = render(tree, parsed, "duckdb")
    assert "unused_status" not in code
    assert "largest_order" not in code
    assert "returned_order_count" not in code
    if name == "gld_customer_leaderboard":
        assert list(tree.find_all(exp.Window))
        assert any(select.args.get("distinct") for select in tree.find_all(exp.Select))
        assert list(tree.find_all(exp.Having))
        assert any(select.args.get("limit") for select in tree.find_all(exp.Select))
    assert warehouse(tree, parsed) == ([column], [types[index]], expected)


def test_leaderboard_ties_and_final_limit_are_exercised(demo, warehouse):
    parsed = parse_model(demo, demo.find("gld_customer_leaderboard").code, expand=True)
    names, _, rows = warehouse(parsed.tree, parsed, ordered=True)
    if rows:  # The same test also runs on the empty-input fixture.
        assert len(rows) == 2
        assert [row[names.index("customer_id")] for row in rows] == [1, 2]
        assert rows[0][names.index("ranked_revenue")] == rows[1][names.index("ranked_revenue")]
        assert [row[names.index("revenue_rank")] for row in rows] == [1, 2]


def test_preview_and_inspection_are_read_only_then_apply_is_idempotent(tmp_path):
    root = tmp_path / "jaffle_shop"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("target", "logs", "extra_review", "dbt_packages"))
    before = snapshot(root)
    preview = invoke(root, "optimize", "--select", SELECT, "--preview")
    assert preview.exit_code == 0, preview.output
    assert "SQL files written: 0" in preview.output
    assert snapshot(root) == before
    for name in NAMES:
        result = invoke(root, "inspect", name, "--compile", "false")
        assert result.exit_code == 0, result.output
    assert snapshot(root) == before
    changes, skipped = optimize(Project(root), select=[SELECT])
    changes.apply()
    second, second_skips = optimize(Project(root), select=[SELECT])
    assert second_skips == skipped
    assert not second.changed()
