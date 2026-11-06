"""Opt-in PostgreSQL target execution; never connect to an implicit local server."""

import os

import pytest

from dbt_extra.inspection import inspect
from dbt_extra.sql.rewrites.engine import optimize_source
from tests.helpers import project, put
from tests.optimizer_cases import RULE_QUERIES, RULE_SCHEMA, assert_rule_exercised
from tests.semantics import assert_equivalent


@pytest.fixture
def postgres():
    dsn = os.environ.get("DBT_EXTRA_POSTGRES_DSN")
    if not dsn:
        pytest.skip("set DBT_EXTRA_POSTGRES_DSN to an isolated PostgreSQL test database")
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as connection:
        # Only session-local temporary tables, automatically removed on close.
        connection.execute("CREATE TEMP TABLE violations(id INTEGER,type_id INTEGER,amount INTEGER)")
        connection.execute("CREATE TEMP TABLE types(id INTEGER,code VARCHAR)")
        yield connection


@pytest.mark.parametrize("rule", RULE_QUERIES)
@pytest.mark.parametrize("empty", ["neither", "outer", "inner", "both"])
def test_postgres_source_rules(postgres, rule, empty):
    if empty not in {"outer", "both"}:
        postgres.execute("INSERT INTO violations VALUES (1,1,2),(1,1,2),(2,2,NULL),(3,NULL,0),(4,9,3)")
    if empty not in {"inner", "both"}:
        postgres.execute("INSERT INTO types VALUES (1,'A'),(1,'A'),(2,NULL),(5,'B')")
    code = RULE_QUERIES[rule]
    outcomes = []
    candidate = optimize_source(code, "postgres", schema=RULE_SCHEMA, outcomes=outcomes)
    assert_rule_exercised(rule, candidate, "postgres", outcomes)
    assert_equivalent(postgres, code, candidate)


CASES = [
    "SELECT v.id,v.amount FROM violations v ORDER BY v.amount NULLS LAST,v.id LIMIT 3 OFFSET 1",
    "SELECT id FROM (SELECT id,type_id FROM violations UNION SELECT id,amount FROM violations) q",
    "SELECT id FROM (SELECT id,type_id,COUNT(*) AS n FROM violations GROUP BY GROUPING SETS((id,type_id),(id),())) q",
    "SELECT v.id FROM violations v LEFT JOIN (SELECT id,COUNT(*) AS n FROM types GROUP BY id) t ON v.type_id=t.id",
    "SELECT id,CAST(amount AS DECIMAL(12,2))+0.00 AS amount FROM violations",
    "SELECT q.k FROM (SELECT 1 AS k,COUNT(*) AS n FROM violations) q WHERE q.k=0",
]


@pytest.mark.parametrize("code", CASES)
@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("mode", ["source", "inspection"])
def test_postgres_boundaries_and_output_contract(native, postgres, code, empty, mode):
    if not empty:
        postgres.execute("INSERT INTO violations VALUES (1,1,2),(1,1,2),(2,2,NULL),(3,NULL,0),(4,9,3)")
        postgres.execute("INSERT INTO types VALUES (1,'A'),(1,'A'),(2,NULL),(5,'B')")
    if mode == "source":
        candidate = optimize_source(code, "postgres", schema=RULE_SCHEMA)
    else:
        put(native, "models/postgres.sql", code)
        p = project(native)
        p.dialect = "postgres"
        candidate = inspect(p, "postgres", compiled=False)[0].sql(dialect="postgres")
    assert_equivalent(postgres, code, candidate)


def test_postgres_error_contract_is_not_hidden_by_a_shared_exception_class(postgres):
    from psycopg.errors import NumericValueOutOfRange

    code = "SELECT (2147483647+1)*0 AS value"
    candidate = optimize_source(code, "postgres")
    assert_equivalent(postgres, code, candidate, expected_error=(NumericValueOutOfRange, "integer out of range"))
