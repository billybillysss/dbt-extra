"""Build original and rewritten temporary projects with the real dbt compiler."""

import importlib.util
import os
import subprocess
import sys

import duckdb
import pytest

from dbt_extra.optimization import optimize
from dbt_extra.project import Project
from tests.helpers import put
from tests.semantics import result


pytestmark = pytest.mark.skipif(os.environ.get("DBT_EXTRA_DBT_TESTS") != "1", reason="set DBT_EXTRA_DBT_TESTS=1 with dbt-duckdb installed")


def build(root):
    command = [sys.executable, "-c", "from dbt.cli.main import dbtRunner; import sys; result=dbtRunner().invoke(sys.argv[1:]); sys.exit(0 if result.success else 1)",
               "build", "--project-dir", str(root), "--profiles-dir", str(root), "--no-partial-parse", "--no-use-colors"]
    environment = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment, timeout=180)
    assert completed.returncode == 0, completed.stdout + completed.stderr


MODELS = {
    "base": "SELECT id,k,amount FROM {{ ref('inputs') }}",
    "rules": """WITH shared AS (SELECT id,k,amount,k AS unused FROM {{ ref('base') }})
        SELECT q.id,1+2 AS sample FROM (SELECT id,k,amount,unused FROM shared) q
        WHERE (q.id=1 AND q.amount>0) OR q.id=2 ORDER BY q.id""",
    "macro_model": "SELECT id,{{ twice('amount') }} AS doubled FROM {{ ref('base') }} WHERE TRUE ORDER BY id,doubled",
    "static_model": "{% set threshold=1 %}SELECT id,amount FROM {{ ref('base') }} WHERE amount>{{ threshold }} ORDER BY id,amount",
    "distinct_model": "SELECT id FROM (SELECT DISTINCT id,amount FROM {{ ref('base') }}) q ORDER BY id",
    "empty_aggregate": "SELECT q.marker FROM (SELECT 7 AS marker,COUNT(*) AS n FROM {{ ref('base') }} WHERE FALSE) q",
    "window_model": "SELECT id,rn FROM (SELECT id,amount,ROW_NUMBER() OVER(PARTITION BY id ORDER BY amount) AS rn FROM {{ ref('base') }}) q WHERE rn<=2 ORDER BY id,rn",
    "exists_model": "SELECT v.id FROM {{ ref('base') }} v WHERE EXISTS(SELECT 1 FROM {{ ref('inputs') }} t WHERE t.k=v.k) ORDER BY v.id",
}


def observe_project(root, database):
    observations = {}
    with duckdb.connect(str(database)) as connection:
        for name in MODELS:
            compiled = root / "target/compiled/shop/models" / f"{name}.sql"
            assert compiled.is_file(), compiled
            # Execute dbt-compiled SQL directly: no parse_model/static interpreter
            # on either side, and compare promised order as well as output types.
            observations[name] = result(connection, compiled.read_text(encoding="utf-8"))
            observations[name + ":stored"] = result(connection, f'SELECT * FROM "{name}"')
    return observations


@pytest.mark.parametrize("expand", [False, True])
def test_real_dbt_build_preserves_compiled_and_materialized_results(tmp_path, expand):
    assert importlib.util.find_spec("dbt") is not None, "dbt-duckdb must be installed when this lane is enabled"
    root = tmp_path / "project"
    database = tmp_path / "warehouse.duckdb"
    put(root, "dbt_project.yml", "name: shop\nversion: '1.0'\nconfig-version: 2\nprofile: shop\nmodel-paths: [models]\nseed-paths: [seeds]\nmacro-paths: [macros]\nmodels:\n  shop:\n    +materialized: table\n")
    put(root, "profiles.yml", "shop:\n  target: test\n  outputs:\n    test:\n      type: duckdb\n      path: '" + database.as_posix() + "'\n      threads: 1\n")
    put(root, "seeds/inputs.csv", "id,k,amount\n1,1,2\n1,1,2\n2,2,4\n3,,0\n4,9,3\n,1,\n")
    put(root, "macros/twice.sql", "{% macro twice(value) %}{{ value }} + {{ value }}{% endmacro %}")
    for name, code in MODELS.items():
        put(root, f"models/{name}.sql", code)
    build(root)
    before = observe_project(root, database)
    changes, skipped = optimize(Project(root, dialect="duckdb"), select=list(MODELS), expand=expand)
    assert not skipped
    applied = {o["rule"] for report in changes.optimization_report.values() for o in report["outcomes"] if o["status"] == "applied"}
    assert {"literal_simplification", "projection_pruning", "predicate_normalization", "subquery_merge"} <= applied
    assert changes.changed(), "A build of unchanged models is not rewrite execution coverage"
    changes.apply()
    assert "EXISTS" in (root / "models/exists_model.sql").read_text().upper()
    build(root)
    assert observe_project(root, database) == before
    assert not optimize(Project(root, dialect="duckdb"), select=list(MODELS), expand=expand)[0].changed()
