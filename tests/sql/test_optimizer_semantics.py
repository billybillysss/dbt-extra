"""Type/coercion regressions and tests proving the equivalence oracle can fail."""

import duckdb
import pytest
from sqlglot import exp, parse_one

from dbt_extra.optimization import optimize
from dbt_extra.sql.rewrites.engine import optimize_source
from dbt_extra.sql.qualification import source_schema
from dbt_extra.sql.rewrites.structural import decorrelate_filter_exists
from tests.helpers import project, put
from tests.semantics import assert_equivalent, render_jinja, result


EXISTS = "SELECT v.id FROM v WHERE EXISTS (SELECT 1 FROM t WHERE t.k=v.k) ORDER BY v.id"
KEY_TYPES = [
    ("INT", "VARCHAR"), ("VARCHAR", "INT"), ("SMALLINT", "INT"),
    ("INT", "BIGINT"), ("DECIMAL(12,2)", "INT"), ("DOUBLE", "INT"),
    ("VARCHAR", "VARCHAR"), ("INT", "INT"), ("BIGINT", "BIGINT"), ("SMALLINT", "SMALLINT"),
    ("TINYINT", "TINYINT"),
]


@pytest.mark.parametrize("outer_type,inner_type", KEY_TYPES)
@pytest.mark.parametrize("empty", ["neither", "outer", "inner", "both", "nulls"])
@pytest.mark.parametrize("evidence", ["complete", "unknown", "absent"])
def test_exists_membership_requires_a_type_proof(outer_type, inner_type, empty, evidence):
    schema = {"v": {"id": "INT", "k": outer_type}, "t": {"k": inner_type}}
    if evidence == "unknown":
        schema = {"v": {"id": "INT", "k": "UNKNOWN"}, "t": {"k": "UNKNOWN"}}
    elif evidence == "absent":
        schema = None
    outcomes = []
    candidate = optimize_source(EXISTS, "duckdb", schema=schema, outcomes=outcomes)
    certified = evidence == "complete" and outer_type == inner_type and outer_type in {"TINYINT", "SMALLINT", "INT", "BIGINT"}
    tree = parse_one(candidate, read="duckdb")
    assert bool(tree.find(exp.In)) == certified
    assert bool(tree.find(exp.Exists)) != certified
    assert any(o["rule"] == "exists_decorrelation" and o["status"] == "applied" for o in outcomes) == certified
    with duckdb.connect() as con:
        con.execute(f"CREATE TABLE v(id INT,k {outer_type})")
        con.execute(f"CREATE TABLE t(k {inner_type})")
        if empty not in {"outer", "both"}:
            rows = [(1, None), (2, None)] if empty == "nulls" else [(1, 1), (1, 1), (2, 2), (3, -1), (4, None), (5, 9)]
            con.executemany("INSERT INTO v VALUES (?,?)", rows)
        if empty not in {"inner", "both"}:
            rows = [(None,)] if empty == "nulls" else [(1,), (1,), (2,), (-1,), (None,)]
            con.executemany("INSERT INTO t VALUES (?)", rows)
        assert_equivalent(con, EXISTS, candidate)
    assert optimize_source(candidate, "duckdb", schema=schema) == candidate


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("invalid", [False, True])
def test_exists_mixed_types_preserve_comparison_conversion_errors(reverse, invalid):
    left, right = ("VARCHAR", "INT") if reverse else ("INT", "VARCHAR")
    code = "SELECT v.id FROM v WHERE EXISTS(SELECT 1 FROM t WHERE v.k=t.k AND t.keep=1) ORDER BY v.id"
    candidate = optimize_source(code, "duckdb", schema={"v": {"id": "INT", "k": left}, "t": {"k": right, "keep": "INT"}})
    assert parse_one(candidate).find(exp.Exists)
    with duckdb.connect() as con:
        con.execute(f"CREATE TABLE v(id INT,k {left})")
        con.execute(f"CREATE TABLE t(k {right},keep INT)")
        string_value = "oops" if invalid else "01"
        con.execute("INSERT INTO v VALUES (1,?)", [string_value if reverse else 1])
        con.execute("INSERT INTO t VALUES (?,1)", [1 if reverse else string_value])
        expected_error = (duckdb.ConversionException, "Could not convert string") if invalid else None
        assert_equivalent(con, code, candidate, expected_error=expected_error)


@pytest.mark.parametrize("kind,bits", [("TINYINT", 8), ("SMALLINT", 16), ("INT", 32), ("BIGINT", 64)])
def test_membership_proof_preserves_integral_extremes(kind, bits):
    schema = {"v": {"id": "INT", "k": kind}, "t": {"k": kind}}
    candidate = optimize_source(EXISTS, "duckdb", schema=schema)
    assert parse_one(candidate).find(exp.In)
    low, high = -(2 ** (bits - 1)), 2 ** (bits - 1) - 1
    with duckdb.connect() as con:
        con.execute(f"CREATE TABLE v(id INT,k {kind}); CREATE TABLE t(k {kind})")
        con.executemany("INSERT INTO v VALUES (?,?)", [(1, low), (1, low), (2, high), (3, None), (4, 0)])
        con.executemany("INSERT INTO t VALUES (?)", [(low,), (low,), (high,), (None,)])
        assert_equivalent(con, EXISTS, candidate)


@pytest.mark.parametrize("expand", [False, True])
def test_project_macro_modes_do_not_guess_physical_key_types(native, expand):
    put(native, "macros/key.sql", "{% macro key(value) %}{{ value }}{% endmacro %}")
    code = "SELECT {{ key('v.id') }} AS id FROM v WHERE EXISTS(SELECT 1 FROM t WHERE t.k=v.k) ORDER BY id"
    path = put(native, "models/type_safety.sql", code)
    changes, skipped = optimize(project(native), select=["type_safety"], expand=expand)
    assert not skipped
    candidate = changes.after[path].decode()
    assert "EXISTS" in candidate.upper()
    with duckdb.connect() as con:
        con.execute("CREATE TABLE v(id INT,k INT); CREATE TABLE t(k VARCHAR)")
        con.execute("INSERT INTO v VALUES (1,1),(2,NULL); INSERT INTO t VALUES ('1'),(NULL)")
        assert_equivalent(con, render_jinja(native, code), render_jinja(native, candidate))
    changes.apply()
    assert not optimize(project(native), select=["type_safety"], expand=expand)[0].changed()


def test_derived_keys_are_not_mistaken_for_declared_base_columns():
    code = "WITH v AS (SELECT id,k FROM u) SELECT v.id FROM v WHERE EXISTS(SELECT 1 FROM t WHERE t.k=v.k)"
    schema = source_schema({"u": {"id": "INT", "k": "INT"}, "t": {"k": "INT"}}, "duckdb")
    original = parse_one(code)
    assert decorrelate_filter_exists(original.copy(), dialect="duckdb", schema=schema) == original


def test_inner_cte_cannot_borrow_a_shadowed_base_table_type():
    code = "WITH t AS (SELECT CAST(k AS VARCHAR) AS k FROM u) SELECT v.id FROM v WHERE EXISTS(SELECT 1 FROM t WHERE t.k=v.k)"
    schema = {"u": {"k": "INT"}, "v": {"id": "INT", "k": "INT"}, "t": {"k": "INT"}}
    candidate = optimize_source(code, "duckdb", schema=schema)
    assert parse_one(candidate).find(exp.Exists)
    with duckdb.connect() as con:
        con.execute("CREATE TABLE u(k INT); CREATE TABLE v(id INT,k INT)")
        con.execute("INSERT INTO u VALUES (1),(1),(NULL); INSERT INTO v VALUES (1,1),(2,NULL)")
        assert_equivalent(con, code, candidate)


@pytest.mark.parametrize("suffix", ["", ";", " -- keep this comment", "; -- keep this comment"])
@pytest.mark.parametrize("expand", [False, True])
def test_project_output_is_embeddable_without_changing_literal_semicolons(native, suffix, expand):
    code = "SELECT ';' AS punctuation,1+2 AS n" + suffix
    path = put(native, "models/embeddable.sql", code)
    changes, skipped = optimize(project(native), select=["embeddable"], expand=expand)
    if suffix.startswith("; --"):
        # SQLGlot represents post-terminator comments as another statement.
        # This unsupported input must remain byte-identical, never lose comments.
        assert "expected one SQL statement" in skipped["model.shop.embeddable"]
        assert path not in changes.after
        assert path.read_text() == code
        return
    assert not skipped
    candidate = changes.after[path].decode()
    with duckdb.connect() as con:
        assert_equivalent(con, code, candidate)
        assert result(con, "SELECT * FROM (\n" + candidate + "\n) model") == result(con, code)
    if "keep this comment" in code:
        assert "keep this comment" in candidate
    changes.apply()
    assert not optimize(project(native), select=["embeddable"], expand=expand)[0].changed()


def test_standalone_optimizer_keeps_statement_terminator():
    assert optimize_source("SELECT ';' AS punctuation", "duckdb").endswith(";\n")


@pytest.mark.parametrize("candidate", [
    "SELECT DISTINCT id FROM t ORDER BY id",  # lost multiplicity
    "SELECT id FROM t ORDER BY id DESC",     # changed promised order
    "SELECT CAST(id AS BIGINT) AS id FROM t ORDER BY id",  # changed type
    "SELECT id AS renamed FROM t ORDER BY id",  # changed interface
    "SELECT id FROM t WHERE id IS NOT NULL ORDER BY id",  # lost NULL
    "SELECT id FROM t ORDER BY id LIMIT 2",   # lost rows
])
def test_oracle_rejects_deliberately_broken_rewrites(candidate):
    with duckdb.connect() as con:
        con.execute("CREATE TABLE t(id INT); INSERT INTO t VALUES (1),(1),(2),(NULL)")
        with pytest.raises(AssertionError):
            assert_equivalent(con, "SELECT id FROM t ORDER BY id", candidate)


def test_unordered_oracle_preserves_bags_without_demanding_accidental_order():
    with duckdb.connect() as con:
        assert result(con, "SELECT * FROM (VALUES (1),(2),(1)) t(id)") == result(
            con, "SELECT * FROM (VALUES (2),(1),(1)) t(id)")


def test_oracle_does_not_accept_two_unexpected_or_different_errors():
    with duckdb.connect() as con:
        with pytest.raises(duckdb.ConversionException):
            assert_equivalent(con, "SELECT CAST('bad' AS INT)", "SELECT CAST('bad' AS INT)")
        with pytest.raises(AssertionError):
            assert_equivalent(con, "SELECT CAST('bad' AS INT)", "SELECT CAST('other' AS INT)",
                              expected_error=(duckdb.ConversionException, "Could not convert string"))
