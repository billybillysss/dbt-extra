"""Opt-in, credential-free target execution; parse/render tests are not this proof."""

import os
from collections import Counter

import pytest
from sqlglot import exp, parse_one

from dbt_extra.inspection import inspect
from dbt_extra.sql.rewrites.engine import optimize_source
from tests.helpers import project, put
from tests.optimizer_cases import RULE_QUERIES, RULE_SCHEMA, assert_rule_exercised


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    if os.environ.get("DBT_EXTRA_SPARK_TESTS") != "1":
        pytest.skip("set DBT_EXTRA_SPARK_TESTS=1 with PySpark and Java installed")
    import pyspark
    from pyspark.sql import SparkSession

    session = (SparkSession.builder.master("local[1]").appName("dbt-extra-regressions")
               .config("spark.ui.enabled", "false")
               .config("spark.sql.shuffle.partitions", "1")
               .config("spark.sql.warehouse.dir", str(tmp_path_factory.mktemp("spark-warehouse")))
               .getOrCreate())
    session.sparkContext.setLogLevel("OFF")
    try:
        assert session.version == pyspark.__version__, "SPARK_HOME must not override the installed PySpark version"
        assert session.version.startswith("4.2."), "This execution lane targets Spark 4.2"
        yield session
    finally:
        session.stop()


CASES = [
    "SELECT q.k FROM (SELECT 1 AS k, COUNT(*) AS n FROM t) q WHERE q.k=0",
    "SELECT (2147483647+1)*0 AS v",
    "SELECT 1+2 AS k, CAST('not-an-integer' AS INT) AS v",
    "SELECT CAST(x AS DECIMAL(12,2))+0.00 AS v, NULL AND x=1 AS n FROM t",
    "SELECT id FROM (SELECT id, ROW_NUMBER() OVER(PARTITION BY id ORDER BY x) rn, unused FROM t) q",
    "SELECT id FROM (SELECT id,x,COUNT(*) n FROM t GROUP BY GROUPING SETS((id,x),(id),())) q",
    "SELECT a.id FROM t a LEFT JOIN t b ON a.id=b.id",
    "SELECT a.id FROM t a LEFT JOIN (SELECT id,COUNT(*) n FROM t GROUP BY id) b ON a.id=b.id",
    "SELECT id FROM (SELECT id,x FROM t UNION SELECT id,unused FROM t) q",
    "WITH s AS (SELECT id,x,unused FROM t) SELECT id FROM s WHERE x>0 UNION ALL SELECT id FROM s WHERE unused IS NOT NULL",
    "SELECT id FROM (SELECT id,(SELECT COUNT(*) FROM t) AS n,unused FROM t) q ORDER BY id NULLS LAST",
]


def observation(spark, sql, *, ordered=False):
    frame = spark.sql(sql)
    rows = [tuple(row) for row in frame.collect()]
    values = rows if ordered else Counter(rows)
    return frame.columns, [field.dataType.simpleString() for field in frame.schema], values


def assert_spark_equivalent(spark, original, candidate, *, ordered=False, expected_error=None):
    if expected_error:
        from pyspark.errors import PySparkException

        errors = []
        for sql in (original, candidate):
            with pytest.raises(PySparkException) as caught:
                observation(spark, sql, ordered=ordered)
            assert caught.value.getCondition() == expected_error
            errors.append(caught.value.getMessageParameters())
        assert errors[0] == errors[1]
    else:
        assert observation(spark, original, ordered=ordered) == observation(spark, candidate, ordered=ordered), candidate


@pytest.mark.parametrize("ansi", [False, True])
@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("mode", ["source", "inspection"])
@pytest.mark.parametrize("code", CASES)
def test_spark_target_semantics(native, spark, ansi, empty, mode, code):
    spark.conf.set("spark.sql.ansi.enabled", str(ansi).lower())
    spark.sql("CREATE OR REPLACE TEMP VIEW t AS SELECT * FROM VALUES "
              "(1,2,CAST(NULL AS INT)),(1,2,NULL),(2,3,4),(NULL,5,6) AS v(id,x,unused) "
              + ("WHERE FALSE" if empty else ""))
    if mode == "source":
        candidate = optimize_source(code, "spark", schema={"t": {"id": "INT", "x": "INT", "unused": "INT"}})
    else:
        put(native, "models/trial.sql", code)
        p = project(native)
        p.dialect = "spark"
        candidate = inspect(p, "trial", compiled=False)[0].sql(dialect="spark")
    ordered = code == CASES[-1]
    expected_error = None
    if ansi and code == CASES[1]:
        expected_error = "ARITHMETIC_OVERFLOW"
    elif ansi and code == CASES[2]:
        expected_error = "CAST_INVALID_INPUT"
    assert_spark_equivalent(spark, code, candidate, ordered=ordered, expected_error=expected_error)


@pytest.mark.parametrize("rule", RULE_QUERIES)
@pytest.mark.parametrize("empty", ["neither", "outer", "inner", "both"])
@pytest.mark.parametrize("ansi", [False, True])
def test_spark_executes_each_enabled_source_rule(spark, rule, empty, ansi):
    spark.conf.set("spark.sql.ansi.enabled", str(ansi).lower())
    spark.sql("CREATE OR REPLACE TEMP VIEW violations AS SELECT * FROM VALUES "
              "(1,1,2),(1,1,2),(2,2,CAST(NULL AS INT)),(3,NULL,0),(4,9,3) AS v(id,type_id,amount) "
              + ("WHERE FALSE" if empty in {"outer", "both"} else ""))
    spark.sql("CREATE OR REPLACE TEMP VIEW types AS SELECT * FROM VALUES "
              "(1,'A'),(1,'A'),(2,CAST(NULL AS STRING)),(5,'B') AS t(id,code) "
              + ("WHERE FALSE" if empty in {"inner", "both"} else ""))
    code = RULE_QUERIES[rule]
    outcomes = []
    candidate = optimize_source(code, "spark", schema=RULE_SCHEMA, outcomes=outcomes)
    assert_rule_exercised(rule, candidate, "spark", outcomes)
    assert_spark_equivalent(spark, code, candidate)


@pytest.mark.parametrize("function", ["isnull", "isnotnull"])
@pytest.mark.parametrize("mode", ["source", "inspection"])
@pytest.mark.parametrize("empty", [False, True])
def test_spark_executes_certified_null_check_pruning(native, spark, function, mode, empty):
    spark.sql("CREATE OR REPLACE TEMP VIEW t AS SELECT * FROM VALUES "
              "(1),(1),(2),(CAST(NULL AS INT)) AS v(id) " + ("WHERE FALSE" if empty else ""))
    code = f"SELECT q.id FROM (SELECT id,{function}(id) AS unused FROM t) q ORDER BY q.id NULLS LAST"
    if mode == "source":
        candidate = optimize_source(code, "spark", schema={"t": {"id": "INT"}})
    else:
        put(native, "models/null_check.sql", code)
        p = project(native)
        p.dialect = "spark"
        candidate = inspect(p, "null_check", compiled=False)[0].sql(dialect="spark")
    assert not parse_one(candidate, read="spark").find(exp.Anonymous)
    assert "unused" not in candidate.lower()
    assert_spark_equivalent(spark, code, candidate, ordered=True)


@pytest.mark.parametrize("ansi", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("invalid", [False, True])
def test_spark_mixed_key_types_retain_exists(spark, ansi, reverse, invalid):
    spark.conf.set("spark.sql.ansi.enabled", str(ansi).lower())
    text = "oops" if invalid else "01"
    left, right = (f"'{text}'", "1") if reverse else ("1", f"'{text}'")
    spark.sql(f"CREATE OR REPLACE TEMP VIEW v AS SELECT {left} AS k")
    spark.sql(f"CREATE OR REPLACE TEMP VIEW u AS SELECT {right} AS k")
    code = "SELECT v.k FROM v WHERE EXISTS(SELECT 1 FROM u WHERE u.k=v.k)"
    schema = {"v": {"k": "VARCHAR" if reverse else "INT"}, "u": {"k": "INT" if reverse else "VARCHAR"}}
    candidate = optimize_source(code, "spark", schema=schema)
    assert parse_one(candidate).find(exp.Exists)
    assert_spark_equivalent(spark, code, candidate, expected_error="CAST_INVALID_INPUT" if ansi and invalid else None)


@pytest.mark.parametrize("kind,bits", [("TINYINT", 8), ("SMALLINT", 16), ("INT", 32), ("BIGINT", 64)])
@pytest.mark.parametrize("ansi", [False, True])
def test_spark_membership_preserves_integral_extremes(spark, kind, bits, ansi):
    spark.conf.set("spark.sql.ansi.enabled", str(ansi).lower())
    low, high = -(2 ** (bits - 1)), 2 ** (bits - 1) - 1
    spark.sql(f"CREATE OR REPLACE TEMP VIEW v AS SELECT id,CAST(k AS {kind}) AS k FROM VALUES "
              f"(1,{low}L),(1,{low}L),(2,{high}L),(3,CAST(NULL AS BIGINT)),(4,0L) AS q(id,k)")
    spark.sql(f"CREATE OR REPLACE TEMP VIEW u AS SELECT CAST(k AS {kind}) AS k FROM VALUES "
              f"({low}L),({low}L),({high}L),(CAST(NULL AS BIGINT)) AS q(k)")
    code = "SELECT v.id FROM v WHERE EXISTS(SELECT 1 FROM u WHERE u.k=v.k) ORDER BY v.id"
    candidate = optimize_source(code, "spark", schema={"v": {"id": "INT", "k": kind}, "u": {"k": kind}})
    assert parse_one(candidate).find(exp.In)
    assert_spark_equivalent(spark, code, candidate, ordered=True)
