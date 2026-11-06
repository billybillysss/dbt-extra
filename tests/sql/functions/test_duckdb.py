"""DuckDB: actual Anonymous gaps with conservative unresolved type policies."""

import duckdb
import pytest
from sqlglot import exp

from dbt_extra.sql.functions import DUCKDB
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", DUCKDB, ids=lambda f: f.name)
def test_duckdb_recognition_and_shape(spec):
    recognition("duckdb", spec)


@pytest.mark.parametrize("spec", DUCKDB, ids=lambda f: f.name)
def test_duckdb_return_types(spec):
    typing("duckdb", spec)


@pytest.mark.parametrize("spec", DUCKDB, ids=lambda f: f.name)
def test_duckdb_rewrite_safety(spec):
    safety("duckdb", spec)


@pytest.mark.parametrize("spec", DUCKDB, ids=lambda f: f.name)
def test_duckdb_metadata_enrichment(native, spec):
    enrichment(native, "duckdb", spec)


def test_duckdb_documented_catalog():
    documentation("duckdb", DUCKDB)


@pytest.mark.parametrize("spec", [f for f in DUCKDB if f.returns], ids=lambda f: f.name)
def test_fixed_return_families_match_offline_binding_without_evaluation(spec):
    with duckdb.connect(":memory:") as con:
        con.execute("CREATE TABLE t(id BIGINT)")
        con.execute("CREATE SEQUENCE seq")
        actual = con.execute("DESCRIBE SELECT " + spec.example + " AS result FROM t").fetchone()[1]
    assert exp.DataType.build(actual, dialect="duckdb") == exp.DataType.build(spec.returns, dialect="duckdb")
