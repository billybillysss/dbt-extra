"""Inspection-only prose relocation must not expand expression safety proofs."""

from collections import Counter

import duckdb
import pytest
from sqlglot import exp, parse_one

from dbt_extra.sql.qualification import qualify_source
from dbt_extra.sql.rewrites.engine import optimize_source
from dbt_extra.sql.rewrites.projections import prune_projections, prune_source_projections
from dbt_extra.sql.rewrites.session import validate_contract
from tests.optimizer_cases import COMMENT_PROJECTION_QUERIES
from tests.semantics import assert_equivalent


SCHEMA = {"t": {"id": "INT", "x": "INT", "unused": "INT"}}
PROSE = " legacy timing columns (backward compat) "
QUERY = "SELECT q.id FROM (SELECT t.id AS id, t.unused AS unused FROM t) q"


def comments(tree):
    return Counter(comment for node in tree.walk() for comment in node.comments or [])


def inner(tree):
    return tree.find(exp.Subquery).this


def non_projection_structure(tree):
    clean = tree.copy()
    for node in clean.walk():
        node.pop_comments()
    for query in clean.find_all(exp.Select):
        query.set("expressions", [exp.Literal.number(1)])
    return clean


@pytest.mark.parametrize("dialect", ["duckdb", "spark"])
def test_only_dead_projection_comments_move_with_duplicate_counts(dialect):
    tree = parse_one(QUERY, read=dialect)
    live, dead = inner(tree).selects
    live.this.add_comments([" live column prose "])
    dead.add_comments([PROSE])
    dead.this.add_comments([PROSE])
    before = tree.copy()
    live_snapshot = live.dump()
    result = prune_projections(tree, dialect=dialect, relocate_comments=True)

    assert result is tree
    assert inner(tree).selects == [live]
    assert inner(tree).selects[0] is live
    assert live.dump() == live_snapshot
    assert inner(tree).comments == [PROSE, PROSE]
    assert comments(tree) == comments(before)
    assert non_projection_structure(tree) == non_projection_structure(before)
    validate_contract(before, tree, dialect)
    qualify_source(tree, SCHEMA, dialect)


@pytest.mark.parametrize("authored,relocate", [(False, False), (True, False), (True, True)])
def test_default_and_authored_policies_keep_commented_projections(authored, relocate):
    tree = parse_one(QUERY)
    inner(tree).selects[1].add_comments([PROSE])
    original = tree.copy()
    kwargs = {"authored": original} if authored else {}
    prune_projections(tree, dialect="duckdb", relocate_comments=relocate, **kwargs)
    assert tree.dump() == original.dump()


def test_source_rewriting_keeps_existing_comment_roots():
    code = "SELECT q.id FROM (SELECT t.id, t.unused /* legacy timing columns */ AS unused FROM t) q"
    authored = parse_one(code, read="duckdb")
    qualified = qualify_source(authored, SCHEMA, "duckdb")
    pruned = prune_source_projections(authored, authored, qualified, dialect="duckdb")
    assert pruned.dump() == authored.dump()
    candidate = parse_one(optimize_source(code, "duckdb", schema=SCHEMA), read="duckdb")
    assert any(p.output_name == "unused" for q in candidate.find_all(exp.Select) for p in q.selects)
    assert comments(candidate) == comments(authored)


@pytest.mark.parametrize("dialect", ["duckdb", "spark"])
@pytest.mark.parametrize("expression", [
    "CAST(t.x AS INT)", "unknown_udf(t.x)", "RAND()", "1 / t.unused", "COALESCE(t.x, 0)",
])
def test_prose_does_not_authorize_fallible_or_effectful_removal(dialect, expression):
    tree = parse_one(f"SELECT q.id FROM (SELECT t.id AS id, {expression} AS risky FROM t) q", read=dialect)
    inner(tree).selects[1].add_comments([PROSE])
    original = tree.copy()
    prune_projections(tree, dialect=dialect, relocate_comments=True)
    assert tree.dump() == original.dump()


@pytest.mark.parametrize("comment", [
    "+ BROADCAST(t)", "! engine directive", "TODO: preserve", "sqlglot", "SQLGLOT meta",
    "noqa", "NoSeC review", "nosemgrep", "", "123 prose", "prose_with_underscores", "prose = value",
])
def test_unfamiliar_and_directive_like_comments_stay_attached(comment):
    tree = parse_one(QUERY)
    inner(tree).selects[1].add_comments([comment])
    original = tree.copy()
    prune_projections(tree, dialect="spark", relocate_comments=True)
    assert tree.dump() == original.dump()


def test_mixed_prose_and_directive_comments_protect_entire_projection():
    tree = parse_one(QUERY)
    inner(tree).selects[1].add_comments([PROSE])
    inner(tree).selects[1].this.add_comments(["noqa"])
    original = tree.copy()
    prune_projections(tree, dialect="spark", relocate_comments=True)
    assert tree.dump() == original.dump()


def test_optimizer_hint_ast_is_not_removed_or_relocated():
    tree = parse_one("SELECT q.id FROM (SELECT /*+ BROADCAST(t) */ t.id AS id, t.unused AS unused FROM t) q", read="spark")
    hint = tree.find(exp.Hint)
    assert hint is not None
    snapshot = hint.dump()
    inner(tree).selects[1].add_comments([PROSE])
    prune_projections(tree, dialect="spark", relocate_comments=True)
    assert tree.find(exp.Hint) is hint
    assert hint.dump() == snapshot
    assert [p.output_name for p in inner(tree).selects] == ["id"]


@pytest.mark.parametrize("code,required", [
    ("SELECT q.id FROM (SELECT t.id, t.x AS x, x + 1 AS used FROM t) q", "x"),
    ("SELECT q.id FROM (SELECT t.id, COUNT(*) AS n FROM t GROUP BY t.id HAVING n > 1) q", "n"),
    ("SELECT q.id FROM (SELECT t.id, ROW_NUMBER() OVER (ORDER BY t.x) AS rn FROM t QUALIFY rn=1) q", "rn"),
    ("SELECT q.id FROM (SELECT t.id, t.x FROM t ORDER BY x LIMIT 2) q", "x"),
])
def test_dependency_roots_still_decide_liveness(code, required):
    tree = parse_one(code, read="duckdb")
    inner(tree).selects[1].add_comments([PROSE])
    before = tree.copy()
    prune_projections(tree, dialect="duckdb", relocate_comments=True)
    assert required in [p.output_name for p in inner(tree).selects]
    assert comments(tree) == comments(before)
    assert non_projection_structure(tree) == non_projection_structure(before)


def test_pruning_never_leaves_an_empty_select():
    tree = parse_one("SELECT 1 AS k FROM (SELECT t.unused AS unused FROM t) q")
    inner(tree).selects[0].add_comments([PROSE])
    before = tree.copy()
    prune_projections(tree, dialect="duckdb", relocate_comments=True)
    assert all(q.selects for q in tree.find_all(exp.Select))
    assert comments(tree) == comments(before)


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("case", COMMENT_PROJECTION_QUERIES)
def test_commented_projection_result_semantics(case, empty):
    code, removed = COMMENT_PROJECTION_QUERIES[case]
    before = parse_one(code, read="duckdb")
    qualify_source(before, SCHEMA, "duckdb")
    candidate = prune_projections(before.copy(), dialect="duckdb", relocate_comments=True)
    validate_contract(before, candidate, "duckdb")
    qualify_source(candidate, SCHEMA, "duckdb")
    assert comments(candidate) == comments(before)
    assert non_projection_structure(candidate) == non_projection_structure(before)
    old_count = sum(len(q.selects) for q in before.find_all(exp.Select))
    new_count = sum(len(q.selects) for q in candidate.find_all(exp.Select))
    assert (new_count < old_count) == removed
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE t(id INT, x INT, unused INT)")
        if not empty:
            connection.execute("INSERT INTO t VALUES (1,2,NULL),(1,2,NULL),(1,3,4),(2,NULL,5),(NULL,6,6)")
        assert_equivalent(connection, code, candidate.sql(dialect="duckdb"))
