"""Small dbt fixtures reproduce alias/expanded-CTE comments without private SQL."""

from collections import Counter

import pytest
from sqlglot import exp, parse_one

from dbt_extra import inspection
from tests.helpers import invoke, project, put, snapshot
from tests.optimizer_cases import COMMENT_PROJECTION_QUERIES


def comments(tree):
    return Counter(c for node in tree.walk() for c in node.comments or [])


@pytest.fixture
def commented_project(native):
    put(native, "models/commented.sql", """
SELECT t.id AS id,
       t.amount /* legacy timing columns (backward compat) */ AS unused
FROM {{ source('raw', 'orders') }} t
""")
    put(native, "models/comment_target.sql", """
WITH expanded AS (SELECT u.id, u.unused FROM {{ ref('commented') }} u)
SELECT e.id, e.unused FROM expanded e
""")
    return native


@pytest.mark.parametrize("dialect", ["duckdb", "spark"])
def test_selected_inspection_relocates_prose_and_preserves_refs(commented_project, dialect):
    p = project(commented_project)
    p.dialect = dialect
    files = snapshot(commented_project)
    before, before_parsed, _ = inspection.inspect(p, "comment_target", ["id"], optimized=False, compiled=False)
    after, after_parsed, outcomes = inspection.inspect(p, "comment_target", ["id"], compiled=False)
    assert [p.output_name for p in after.selects] == ["id"]
    assert not any(p.output_name == "unused" for q in after.find_all(exp.Select) for p in q.selects)
    assert comments(after) == comments(before)
    assert any("legacy timing columns (backward compat)" in c for c in comments(after))
    assert after_parsed.refs == before_parsed.refs
    assert any(o["rule"] == "projection_pruning" and o["status"] == "applied" for o in outcomes)
    assert snapshot(commented_project) == files


@pytest.mark.parametrize("flags", [(), ("--expand", "false"), ("--optimize", "false")])
def test_comment_fixture_cli_modes_complete_without_writes(commented_project, flags):
    files = snapshot(commented_project)
    result = invoke(commented_project, "inspect", "comment_target", "--columns", "id", *flags)
    assert result.exit_code == 0, result.output
    assert "SQL did not round-trip" not in result.output
    assert snapshot(commented_project) == files


@pytest.mark.parametrize("dialect", ["duckdb", "spark"])
@pytest.mark.parametrize("case", COMMENT_PROJECTION_QUERIES)
def test_commented_query_shapes_pass_full_inspection_offline(native, dialect, case):
    code, _ = COMMENT_PROJECTION_QUERIES[case]
    put(native, "models/comment_shape.sql", code)
    p = project(native)
    p.dialect = dialect
    original = parse_one(code, read=dialect)
    tree, _, outcomes = inspection.inspect(p, "comment_shape", compiled=False)
    assert [p.output_name for p in tree.selects] == [p.output_name for p in original.selects]
    assert comments(tree) == comments(original)
    if case in {"subquery", "single_cte", "shared_cte", "left_fanout"}:
        assert any(o["rule"] == "projection_pruning" and o["status"] == "applied" for o in outcomes)


@pytest.mark.parametrize("corruption", ["comments", "bindings"])
def test_comment_aware_pruning_still_rolls_back_invalid_candidates(commented_project, monkeypatch, corruption):
    prune = inspection.prune_projections

    def broken(tree, **kwargs):
        tree = prune(tree, **kwargs)
        if corruption == "comments":
            for node in tree.walk():
                node.pop_comments()
        else:
            tree.selects[0].this.set("this", exp.to_identifier("missing_binding"))
        return tree

    monkeypatch.setattr(inspection, "prune_projections", broken)
    p = project(commented_project)
    before = inspection.inspect(p, "comment_target", ["id"], optimized=False, compiled=False)[0]
    after, _, outcomes = inspection.inspect(p, "comment_target", ["id"], compiled=False)
    assert [p.output_name for p in after.selects] == ["id"]
    assert comments(after) == comments(before)
    assert "missing_binding" not in after.sql()
    assert any(o["rule"] == "projection_pruning" and o["status"] == "rolled_back" for o in outcomes)
