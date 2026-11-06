"""Candidate comment preservation is separate from serializer comment fidelity."""

import pytest
from sqlglot import exp, parse_one

from dbt_extra.sql.renderer import sql
from dbt_extra.sql.rewrites import session
from dbt_extra.sql.rewrites.session import RejectedCandidate, validate_contract


@pytest.mark.parametrize("dialect", ["spark", "duckdb"])
@pytest.mark.parametrize("cte", [False, True])
def test_comment_reattachment_round_trips_without_mutating_inputs(dialect, cte):
    code = "SELECT t.id AS id FROM t"
    if cte:
        code = f"WITH expanded AS ({code}) SELECT id FROM expanded"
    before = parse_one(code, read=dialect)
    projection = list(before.find_all(exp.Select))[-1].selects[0]
    projection.add_comments([" legacy timing columns (backward compat) "])
    after = before.copy()
    projection = list(after.find_all(exp.Select))[-1].selects[0]
    projection.this.add_comments(projection.pop_comments())
    snapshots = [tree.dump() for tree in (before, after)]
    rendered = [sql(tree, dialect) for tree in (before, after)]

    # Exercise the actual parser/generator attachment instability, not just an
    # equality check on two already-normalized renderings.
    assert sql(parse_one(rendered[1], read=dialect), dialect) != rendered[1]
    validate_contract(before, after, dialect)
    assert [tree.dump() for tree in (before, after)] == snapshots
    assert [sql(tree, dialect) for tree in (before, after)] == rendered


def test_comment_moves_from_root_select_to_expanded_cte_on_reparse():
    before = parse_one("WITH expanded AS (SELECT id FROM t) SELECT id FROM expanded", read="spark")
    before.add_comments([" expanded from upstream "])
    after = before.copy()
    snapshot = after.dump()
    reparsed = parse_one(sql(after, "spark"), read="spark")
    assert before.comments and not reparsed.comments
    assert reparsed.find(exp.CTE).comments == before.comments
    assert sql(reparsed, "spark") != sql(after, "spark")
    validate_contract(before, after, "spark")
    assert after.dump() == snapshot


def test_serializer_comment_loss_is_not_a_candidate_comment_loss_check():
    before = parse_one("WITH expanded AS (SELECT id FROM t) SELECT id FROM expanded", read="spark")
    before.find(exp.CTE).this.add_comments([" expanded from upstream "])
    after = before.copy()
    snapshot = after.dump()
    reparsed = parse_one(sql(after, "spark"), read="spark")
    assert not any(n.comments for n in reparsed.walk())
    # Deliberate boundary: candidate comments match, although SQLGlot loses a
    # nested SELECT comment during rendering/reparsing (a separate upstream bug).
    validate_contract(before, after, "spark")
    assert before.dump() == snapshot == after.dump()


@pytest.mark.parametrize("candidate", ["SELECT a AS renamed, b FROM t", "SELECT b, a FROM t"])
def test_output_names_and_order_still_rejected(candidate):
    with pytest.raises(RejectedCandidate, match="output names or order changed"):
        validate_contract(parse_one("SELECT a, b FROM t"), parse_one(candidate), "spark")


@pytest.mark.parametrize("before_count,after_count", [(1, 0), (2, 1), (1, 2)])
def test_comment_multiset_changes_still_rejected(before_count, after_count):
    before = parse_one("SELECT a FROM t")
    after = before.copy()
    # Separate nodes ensure duplicate occurrences are not parser-normalized.
    for node in list(before.walk())[:before_count]:
        node.add_comments([" same prose "])
    for node in list(after.walk())[:after_count]:
        node.add_comments([" same prose "])
    with pytest.raises(RejectedCandidate, match="SQL comments would be discarded"):
        validate_contract(before, after, "spark")


def test_changed_comment_text_still_rejected():
    before, after = parse_one("SELECT a FROM t"), parse_one("SELECT a FROM t")
    before.add_comments([" original prose "])
    after.add_comments([" changed prose "])
    with pytest.raises(RejectedCandidate, match="SQL comments would be discarded"):
        validate_contract(before, after, "spark")


def test_executable_round_trip_instability_still_rejected(monkeypatch):
    before = parse_one("SELECT a FROM t WHERE a > 0")
    monkeypatch.setattr(session, "read_query", lambda *args: parse_one("SELECT a FROM t WHERE a > 1"))
    with pytest.raises(RejectedCandidate, match="SQL did not round-trip"):
        validate_contract(before, before.copy(), "spark")
