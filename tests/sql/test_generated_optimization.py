"""Seeded query/data variation exercises rule interactions and asymmetric inputs."""

import random

import duckdb
import pytest

from dbt_extra.inspection import inspect
from dbt_extra.sql.rewrites.engine import optimize_source
from tests.helpers import project, put
from tests.semantics import assert_equivalent


SCHEMA = {"t": {"id": "INT", "x": "INT", "unused": "INT"}, "u": {"id": "INT", "x": "INT"}}


def queries(randomizer):
    key = randomizer.choice([-1, 0, 1, 2])
    threshold = randomizer.choice([-1, 0, 1, 2147483647])
    return [
        f"SELECT q.id,1+2 AS sample FROM (SELECT id,x,unused FROM t) q WHERE (q.id={key} AND q.x>{threshold}) OR q.id=2",
        f"SELECT q.id FROM (SELECT DISTINCT id,x FROM t) q WHERE q.id>{key} AND TRUE ORDER BY q.id",
        "WITH shared AS (SELECT id,x,unused FROM t) SELECT id FROM shared WHERE x>0 UNION ALL SELECT id FROM shared WHERE unused IS NULL",
        "SELECT a.id,b.x,c.x AS other FROM t a CROSS JOIN t b JOIN u c ON a.id=c.id AND b.id=c.id",
        "SELECT a.id,a.n,b.n AS other FROM (SELECT id,COUNT(*) AS n FROM t GROUP BY id) a JOIN (SELECT id,COUNT(*) AS n FROM t GROUP BY id) b ON a.id=b.id",
        f"SELECT id FROM t WHERE x={threshold} UNION ALL SELECT id FROM t WHERE x<>{threshold}",
        "SELECT a.id FROM t a WHERE EXISTS(SELECT 1 FROM u b WHERE b.id=a.id AND b.x>0)",
        "SELECT a.id FROM t a LEFT JOIN (SELECT id,COUNT(*) AS n FROM u GROUP BY id) b ON a.id=b.id",
        "SELECT id FROM (SELECT id,x,COUNT(*) AS n FROM t GROUP BY GROUPING SETS((id,x),(id),())) q",
        "SELECT id,rn FROM (SELECT id,x,unused,ROW_NUMBER() OVER(PARTITION BY id ORDER BY x,unused) AS rn FROM t) q WHERE rn<=2 ORDER BY id NULLS LAST,rn",
        "SELECT id,x FROM t ORDER BY x NULLS LAST,id NULLS LAST,unused NULLS LAST LIMIT 5 OFFSET 1",
        "SELECT id FROM (SELECT id,x FROM t EXCEPT ALL SELECT id,x FROM t WHERE x>0) q",
        "SELECT id FROM (SELECT id,x FROM t INTERSECT ALL SELECT id,x FROM t WHERE x>0) q",
        "SELECT id FROM t WHERE id NOT IN (SELECT id FROM u)",
    ]


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("empty", ["neither", "outer", "inner", "both"])
@pytest.mark.parametrize("mode", ["source", "inspection"])
def test_seeded_rule_compositions(native, seed, empty, mode):
    randomizer = random.Random(seed)
    ids = [None, -1, 0, 1, 2, 9]
    values = [None, -2147483648, -1, 0, 1, 2, 2147483647]
    outer = [(randomizer.choice(ids), randomizer.choice(values), randomizer.choice(ids)) for _ in range(12)]
    inner = [(randomizer.choice(ids), randomizer.choice(values)) for _ in range(8)]
    outer += outer[:3] + [(None, None, None)]
    inner += inner[:3] + [(None, None)]
    with duckdb.connect() as con:
        con.execute("CREATE TABLE t(id INT,x INT,unused INT); CREATE TABLE u(id INT,x INT)")
        if empty not in {"outer", "both"}:
            con.executemany("INSERT INTO t VALUES (?,?,?)", outer)
        if empty not in {"inner", "both"}:
            con.executemany("INSERT INTO u VALUES (?,?)", inner)
        for code in queries(randomizer):
            if mode == "source":
                candidate = optimize_source(code, "duckdb", schema=SCHEMA)
                assert optimize_source(candidate, "duckdb", schema=SCHEMA) == candidate
            else:
                put(native, "models/generated.sql", code)
                candidate = inspect(project(native), "generated", compiled=False)[0].sql(dialect="duckdb")
            assert_equivalent(con, code, candidate)


def test_composition_actually_applies_multiple_rules():
    # Keep this positive control inside movement's nonnegative-literal boundary;
    # the seeded cases separately exercise retained negative/overflow boundaries.
    code = "SELECT q.id,1+2 AS sample FROM (SELECT id,x,unused FROM t) q WHERE (q.id=1 AND q.x>0) OR q.id=2"
    outcomes = []
    optimize_source(code, "duckdb", schema=SCHEMA, outcomes=outcomes)
    applied = {o["rule"] for o in outcomes if o["status"] == "applied"}
    assert {"projection_pruning", "literal_simplification", "predicate_normalization", "subquery_merge"} <= applied
