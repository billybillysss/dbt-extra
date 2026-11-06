"""Keep the reviewed, offline remaining-dialect inventory reproducible."""

from pathlib import Path
import runpy

import pytest


AUDITOR = runpy.run_path(str(Path(__file__).resolve().parents[3] / "scripts/audit_sql_functions.py"))
CASES = tuple(AUDITOR["cases"]())


def test_inventory_covers_each_remaining_dialect_without_duplicate_examples():
    assert {case.dialect for case in CASES} == {
        "duckdb", "postgres", "snowflake", "bigquery", "fabric", "databricks",
        "redshift", "trino", "athena",
    }
    assert len({(case.dialect, case.expression) for case in CASES}) == len(CASES)
    for case in CASES:
        assert case.arity and case.policy
        assert case.source.startswith("https://")
        assert case.kind in {"scalar", "aggregate", "window", "generator"}
        assert case.volatility in {"immutable", "stable", "volatile", "unknown"}


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case.dialect}:{case.expression}")
def test_reviewed_sqlglot_observation(case):
    assert AUDITOR["observe"](case) == (case.ast, case.inferred, case.classification)


def test_check_mode_exits_unsuccessfully_on_a_changed_observation(monkeypatch, capsys):
    namespace = AUDITOR["main"].__globals__
    monkeypatch.setitem(namespace, "cases", lambda: CASES[:1])
    monkeypatch.setitem(namespace, "observe", lambda _: ("Changed", "unresolved", "recognition_gap"))
    monkeypatch.setattr("sys.argv", ["audit_sql_functions.py", "--check"])
    with pytest.raises(SystemExit) as exc:
        AUDITOR["main"]()
    assert exc.value.code == 1
    assert "Review dependency changes" in capsys.readouterr().err


def test_native_audit_does_not_measure_local_catalog_types():
    from dbt_extra.analysis.type_inference import inferred_types
    from dbt_extra.sql.parser import parse_authored

    case = next(c for c in CASES if c.dialect == "postgres" and c.expression == "pg_backend_pid()")
    tree = parse_authored("SELECT " + case.expression + " AS result", case.dialect).tree
    assert inferred_types(tree, {}, case.dialect) == {"result": "INT"}
    assert AUDITOR["observe"](case) == ("Anonymous", "unresolved", "recognition_gap")
