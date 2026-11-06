"""Self-contained semantic counterexamples and positive partial-safe assertions."""

import duckdb
import pytest
from sqlglot import exp, parse_one
from sqlglot.errors import OptimizeError

from dbt_extra.inspection import inspect
from dbt_extra.sql.rewrites.engine import optimize_source
from dbt_extra.sql.safety import function_properties
from dbt_extra.sql.rewrites.session import Checkpoints, Outcomes, validate_contract
from tests.helpers import project, put
from tests.semantics import assert_equivalent


SCHEMA = {"t": {"id": "INTEGER", "x": "INTEGER", "unused": "INTEGER"}}
CASES = {
    "aggregate_barrier": "SELECT q.k FROM (SELECT 1 AS k, COUNT(*) AS n FROM t) q WHERE q.k = 0",
    "independent": """WITH safe AS (SELECT a.id FROM (SELECT id, unused FROM t) a WHERE a.id > 1),
        risky AS (SELECT COUNT(*) AS n FROM t)
        SELECT s.id FROM safe s CROSS JOIN risky r""",
    "overflow": "SELECT (2147483647 + 1) * 0 AS v",
    "shared": """WITH shared AS (SELECT id, x, unused FROM t)
        SELECT id FROM shared WHERE x > 0 UNION ALL SELECT id FROM shared WHERE unused IS NOT NULL""",
    "qualify": """SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY id ORDER BY x) AS rn,
        unused FROM t QUALIFY rn = 1) q""",
    "window": "SELECT id FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY x) AS rn, unused FROM t) q",
    "window_sum": "SELECT id FROM (SELECT id, SUM(x) OVER (PARTITION BY id) AS s, unused FROM t) q",
    "nested_aggregate": "SELECT id FROM (SELECT id, (SELECT COUNT(*) FROM t) AS n, unused FROM t) q",
    "grouped": "SELECT id FROM (SELECT id, COUNT(*) n, unused FROM t GROUP BY id, unused) q",
    "grouping_sets": "SELECT id FROM (SELECT id, x, COUNT(*) n FROM t GROUP BY GROUPING SETS ((id,x),(id),())) q",
    "ordinal_group": "SELECT x FROM (SELECT id,x,unused FROM t GROUP BY 1,2,3 ORDER BY 2,1) q",
    "ordinal_order": "SELECT x FROM (SELECT id,x,unused FROM t ORDER BY 2,1 LIMIT 2 OFFSET 1) q",
    "order_all": "SELECT x FROM (SELECT id,x,unused FROM t ORDER BY ALL LIMIT 2) q",
    "union_distinct": "SELECT id FROM (SELECT id,x FROM t UNION SELECT id,unused FROM t) q",
    "union_all": "SELECT id FROM (SELECT id,x FROM t UNION ALL SELECT id,unused FROM t) q",
    "left_duplicates": "SELECT a.id FROM t a LEFT JOIN t b ON a.id=b.id",
    "left_unique": "SELECT a.id FROM t a LEFT JOIN (SELECT id, COUNT(*) n FROM t GROUP BY id) b ON a.id=b.id",
    "left_wrong_grain": "SELECT a.id FROM t a LEFT JOIN (SELECT id,x FROM t GROUP BY id,x) b ON a.id=b.id",
    "correlation": "SELECT a.id, 1+2 AS k FROM t a WHERE EXISTS(SELECT 1 FROM t b WHERE b.x=a.x LIMIT 1)",
    "scalar_error": "SELECT (SELECT x FROM t) AS v, 1+2 AS k",
    "fallible_unused": "SELECT id FROM (SELECT id, CAST(x AS SMALLINT) AS risky, unused FROM t) q",
    "decimal": "SELECT (CAST(x AS DECIMAL(12,2)) + 0.00) AS d, NULL AND x=1 AS n FROM t",
    "generator": "SELECT id FROM (SELECT id, UNNEST([x,unused]) AS v FROM t) q",
    "unnamed_computed": "SELECT ABS(1+2), COALESCE(NULL, 2+3) FROM t",
    "final_order": "SELECT id,x FROM t ORDER BY x NULLS LAST,id NULLS LAST LIMIT 4 OFFSET 1",
}


@pytest.mark.parametrize("mode", ["source", "inspection"])
@pytest.mark.parametrize("empty", [True, False])
@pytest.mark.parametrize("case", CASES)
def test_differential_counterexamples(native, mode, empty, case):
    code = CASES[case]
    if mode == "source":
        candidate = optimize_source(code, "duckdb", schema=SCHEMA)
    else:
        put(native, "models/trial.sql", code)
        candidate = inspect(project(native), "trial", compiled=False)[0].sql(dialect="duckdb")
    with duckdb.connect() as con:
        con.execute("CREATE TABLE t(id INTEGER, x INTEGER, unused INTEGER)")
        if not empty:
            con.execute("INSERT INTO t VALUES (1,2,NULL),(1,2,NULL),(1,3,4),(2,NULL,5),(NULL,6,6),(3,40000,7)")
        expected_error = None
        if case == "overflow":
            expected_error = (duckdb.OutOfRangeException, "Overflow in addition")
        elif case == "scalar_error" and not empty:
            expected_error = (duckdb.InvalidInputException, "More than one row returned by a subquery")
        assert_equivalent(con, code, candidate, expected_error=expected_error)
    tree = parse_one(candidate, read="duckdb")
    if case in {"window", "window_sum", "nested_aggregate", "qualify"}:
        assert all("unused" not in [p.output_name for p in s.selects] for s in tree.find_all(exp.Select))
    if case == "qualify":
        assert tree.find(exp.Window) and tree.find(exp.Qualify)
    if case == "independent":
        assert not tree.find(exp.Subquery), candidate  # positive structural work beside the aggregate
    if case in {"left_duplicates", "left_wrong_grain"}:
        assert tree.find(exp.Join)
    if case == "left_unique" and mode == "inspection":
        assert not tree.find(exp.Join)


@pytest.mark.parametrize("mode", ["source", "inspection"])
def test_unknown_does_not_block_independent_expression(native, mode):
    code = "SELECT 1+2 AS k, mystery(x) AS opaque FROM t WHERE TRUE"
    outcomes = []
    if mode == "source":
        candidate = optimize_source(code, "duckdb", schema=SCHEMA, outcomes=outcomes)
    else:
        put(native, "models/trial.sql", code)
        tree, _, outcomes = inspect(project(native), "trial", compiled=False)
        candidate = tree.sql(dialect="duckdb")
    tree = parse_one(candidate, read="duckdb")
    assert tree.selects[0].unalias() == exp.Literal.number(3)
    assert not tree.find(exp.Where)
    assert len(list(tree.find_all(exp.Anonymous))) == 1
    assert any(o["status"] == "applied" and o["rule"] == "literal_simplification" for o in outcomes)
    assert any(o["status"] == "blocked" and o["reason_code"] == "evaluation_boundary" for o in outcomes)


@pytest.mark.parametrize("mode", ["source", "inspection"])
def test_real_rule_partial_mutation_rolls_back(native, monkeypatch, mode):
    from dbt_extra.sql.rewrites import pipeline

    def broken(tree, **kwargs):
        tree.set("where", exp.Where(this=exp.false()))
        tree.selects[0].set("alias", exp.to_identifier("corrupted"))
        raise OptimizeError("injected recoverable rule failure")

    monkeypatch.setattr(pipeline, "pushdown_safe_predicates", broken)
    code = "SELECT 1+2 AS k, id FROM t WHERE id > 0"
    outcomes = []
    if mode == "source":
        candidate = optimize_source(code, "duckdb", schema=SCHEMA, outcomes=outcomes)
    else:
        put(native, "models/trial.sql", code)
        tree, _, outcomes = inspect(project(native), "trial", compiled=False)
        candidate = tree.sql(dialect="duckdb")
    tree = parse_one(candidate, read="duckdb")
    assert tree.selects[0].output_name == "k" and tree.selects[0].unalias() == exp.Literal.number(3)
    assert tree.args["where"].find(exp.GT)
    assert "corrupted" not in candidate
    assert any(o["status"] == "rolled_back" and o["rule"] == "predicate_pushdown" for o in outcomes)


def test_failed_analysis_never_authorizes_dependent_rule_and_invalidates():
    tree = parse_one("SELECT 1+2 AS k")
    outcomes = Outcomes()
    session = Checkpoints(tree, "duckdb", outcomes, validate=lambda t: validate_contract(tree, t, "duckdb"))

    def failed(t):
        t.set("expressions", [])
        raise OptimizeError("failed proof")

    assert not session.attempt("proof", failed, provides=("proof",))
    assert not session.attempt("dependent", lambda t: pytest.fail("dependent rule ran"), requires=("proof",))
    session.capabilities.add("bindings")
    assert session.attempt("independent", lambda t: t.transform(lambda n: exp.Literal.number(3) if isinstance(n, exp.Add) else n),
                           invalidates=("bindings",))
    assert session.generation == 1 and "bindings" not in session.capabilities
    assert session.tree.selects[0].unalias() == exp.Literal.number(3)
    with pytest.raises(KeyError):
        session.attempt("programming_defect", lambda t: {}["bug"])


def test_properties_do_not_conflate_recognition_with_effect_safety():
    unknown = function_properties(parse_one("mystery(x)"))
    assert not unknown.known and unknown.may_raise and unknown.kind == "unknown"
    assert function_properties(parse_one("SUM(x)")).may_raise
    assert function_properties(parse_one("CURRENT_TIMESTAMP")).volatility == "statement_stable"
    assert function_properties(parse_one("RANDOM()", read="duckdb")).volatility == "volatile"


@pytest.mark.parametrize("mode", ["source", "inspection"])
@pytest.mark.parametrize("expression", ["mystery(x)", "random()", "CAST(x AS SMALLINT)", "x+2147483647"])
def test_qualification_does_not_duplicate_alias_evaluation(native, mode, expression):
    code = f"SELECT {expression} AS z, z AS y, 1+2 AS k FROM t"
    if mode == "source":
        candidate = optimize_source(code, "duckdb", schema=SCHEMA)
    else:
        put(native, "models/trial.sql", code)
        candidate = inspect(project(native), "trial", compiled=False)[0].sql(dialect="duckdb")
    tree = parse_one(candidate, read="duckdb")
    assert isinstance(tree.selects[1].unalias(), exp.Column), candidate
    assert tree.selects[1].unalias().name == "z"
    assert tree.selects[2].unalias() == exp.Literal.number(3)


@pytest.mark.parametrize("mode", ["source", "inspection"])
@pytest.mark.parametrize("filter", [False, True])
def test_join_removal_retains_implicit_coercion_errors(native, mode, filter):
    rhs = "SELECT id, COUNT(*) n FROM u" + (" WHERE bad > 0" if filter else "") + " GROUP BY id"
    code = f"SELECT a.id, 1+2 AS k FROM t a LEFT JOIN ({rhs}) b ON a.id=b.id"
    if mode == "source":
        candidate = optimize_source(code, "duckdb", schema={**SCHEMA, "u": {"id": "VARCHAR", "bad": "VARCHAR"}})
    else:
        put(native, "models/trial.sql", code)
        candidate = inspect(project(native), "trial", compiled=False)[0].sql(dialect="duckdb")
    assert parse_one(candidate, read="duckdb").find(exp.Join)
    with duckdb.connect() as con:
        con.execute("CREATE TABLE t(id INTEGER, x INTEGER, unused INTEGER)")
        con.execute("INSERT INTO t VALUES (1,2,3)")
        con.execute("CREATE TABLE u(id VARCHAR, bad VARCHAR)")
        con.execute("INSERT INTO u VALUES ('oops','oops')")
        expected_error = ((duckdb.BinderException, "Cannot compare values of type VARCHAR") if filter
                          else (duckdb.ConversionException, "Could not convert string"))
        assert_equivalent(con, code, candidate, expected_error=expected_error)


@pytest.mark.parametrize("mode", ["source", "inspection"])
@pytest.mark.parametrize("predicate", ["TRUE OR bad > 0", "FALSE AND bad > 0", "bad = 0 OR bad <> 0"])
def test_predicate_rewrites_do_not_erase_implicit_coercion_errors(native, mode, predicate):
    code = f"SELECT id, 1+2 AS k FROM t WHERE {predicate}"
    outcomes = []
    if mode == "source":
        candidate = optimize_source(code, "duckdb", schema={"t": {"id": "INT", "bad": "VARCHAR"}}, outcomes=outcomes)
    else:
        put(native, "models/trial.sql", code)
        tree, _, outcomes = inspect(project(native), "trial", compiled=False)
        candidate = tree.sql(dialect="duckdb")
    with duckdb.connect() as con:
        con.execute("CREATE TABLE t(id INTEGER, bad VARCHAR)")
        con.execute("INSERT INTO t VALUES (1,'oops')")
        expected_error = ((duckdb.ConversionException, "Could not convert string") if predicate.startswith("bad")
                          else (duckdb.BinderException, "Cannot compare values of type VARCHAR"))
        assert_equivalent(con, code, candidate, expected_error=expected_error)
    assert parse_one(candidate, read="duckdb").selects[1].unalias() == exp.Literal.number(3)
    if predicate.startswith(("TRUE", "FALSE")):
        assert any(o["status"] == "rolled_back" and "predicate evaluation" in o["reason"] for o in outcomes)
    else:
        assert parse_one(candidate, read="duckdb").find(exp.EQ)
        assert parse_one(candidate, read="duckdb").find(exp.NEQ)


def test_wildcard_qualification_does_not_duplicate_fallible_alias(native):
    code = "SELECT * FROM (SELECT mystery(x) AS z, z AS y, 1+2 AS k FROM t) q"
    put(native, "models/trial.sql", code)
    tree, _, _ = inspect(project(native), "trial", compiled=False)
    assert len(list(tree.find_all(exp.Anonymous))) == 1


def test_authored_qualification_failure_keeps_prior_safe_checkpoint(monkeypatch):
    from dbt_extra.sql.rewrites import engine
    from dbt_extra.errors import SpecError

    def failed(*args, **kwargs):
        raise SpecError("injected unavailable bindings")

    monkeypatch.setattr(engine, "qualify_source", failed)
    code = "SELECT a.id, 1+2 AS k FROM t a WHERE EXISTS(SELECT 1 FROM t b WHERE b.id=a.id)"
    outcomes = []
    candidate = optimize_source(code, "duckdb", schema=SCHEMA, outcomes=outcomes)
    tree = parse_one(candidate, read="duckdb")
    assert tree.find(exp.In) and not tree.find(exp.Exists)
    assert tree.selects[1].unalias() == exp.Literal.number(3)
    assert any(o["rule"] == "qualification" and o["status"] == "rolled_back" for o in outcomes)
    assert any(o["rule"] == "projection_pruning" and o["status"] == "blocked" for o in outcomes)
