"""Generated dbt graph, temporal grain, evidence and expansion regressions."""

from collections import Counter

import duckdb
import pytest
from sqlglot import exp

from dbt_extra.errors import SpecError
from dbt_extra.inspection import inspect
from dbt_extra.optimization import optimize
from dbt_extra.project.model_sql import parse_model
from tests.helpers import invoke, project, put, snapshot
from tests.semantics import result as observe
from tests.synthetic import executable, load_relations, synthetic_project


@pytest.mark.parametrize("empty", [True, False])
def test_generated_fact_temporal_differential(tmp_path, empty):
    root = synthetic_project(tmp_path)
    before = snapshot(root)
    p = project(root)
    full, parsed, _ = inspect(p, "fact_metrics", optimized=False, compiled=False)
    sql = "SELECT selected_metric FROM (" + executable(full, parsed) + ") baseline"
    selected, parsed, issues = inspect(p, "fact_metrics", columns=["selected_metric"], compiled=False)
    with duckdb.connect() as con:
        load_relations(con, empty=empty)
        assert observe(con, executable(selected, parsed)) == observe(con, sql)
        if not empty:
            assert observe(con, sql)[2] == Counter([(2,), (0,), (0,), (0,)])
    assert [p.output_name for p in selected.selects] == ["selected_metric"]
    assert any(i.get("rule") == "static_jinja" or "runtime_boundary" in i.get("resource_id", "") for i in issues)
    assert any(i.get("status") == "applied" for i in issues)
    assert snapshot(root) == before
    result = invoke(root, "inspect", "fact_metrics", "--columns", "selected_metric", "--compile", "false")
    assert result.exit_code == 0, result.output
    assert "selected_metric" in result.output and "runtime_boundary" in result.output


@pytest.mark.parametrize("expanded,optimized", [(False, False), (False, True), (True, False), (True, True)])
def test_expansion_selection_and_explicit_boundary_independent(tmp_path, expanded, optimized):
    root = synthetic_project(tmp_path)
    p = project(root)
    tree, parsed, issues = inspect(p, "fact_metrics", columns=["selected_metric"], boundaries=["events"],
                                 expanded=expanded, optimized=optimized, compiled=False)
    assert tree.selects[0].output_name == "selected_metric"
    surviving = {parsed.refs[t.name].args[-1] for t in tree.find_all(exp.Table) if t.name in parsed.refs}
    assert ("events" if expanded else "temporal") in surviving
    if expanded:
        assert any(i.get("reason") == "explicit boundary" for i in issues)


def test_authored_templates_runtime_and_complete_schema_contract(tmp_path):
    root = synthetic_project(tmp_path)
    original = (root / "models/static_metrics.sql").read_bytes()
    changes, skipped = optimize(project(root), select=["static_metrics", "runtime_boundary", "temporal"])
    assert "model.synthetic.runtime_boundary" in skipped
    assert changes.after[root / "models/static_metrics.sql"] == original
    assert changes.optimization_report["model.synthetic.static_metrics"]["outcomes"][0]["reason_code"] == "authored_template_boundary"
    assert "model.synthetic.temporal" in changes.optimization_report
    changes, skipped = optimize(project(root), select=["static_metrics"], expand=True)
    assert not skipped
    assert b"{%" not in changes.after[root / "models/static_metrics.sql"]
    put(root, "models/documented_star.sql", "SELECT * FROM {{ source('raw','events') }}")
    with pytest.raises(SpecError, match="requires known output columns"):
        inspect(project(root), "documented_star", columns=["id"], compiled=False)


def test_operation_caches_parse_each_resource_once_and_counts_boundaries(tmp_path, monkeypatch):
    from dbt_extra import inspection
    from dbt_extra.analysis import expansion
    root = synthetic_project(tmp_path, repeats=12)
    calls = Counter()
    original = expansion.parse_model

    def parse(p, code, context, **kwargs):
        calls[context] += 1
        return original(p, code, context, **kwargs)

    monkeypatch.setattr(expansion, "parse_model", parse)
    tree, _, issues = inspect(project(root), "fact_metrics", columns=["selected_metric"], compiled=False)
    assert calls and max(calls.values()) == 1
    events = [i for i in issues if i.get("rule") == "expansion" and i["resource_id"].endswith(".events")]
    assert len(events) == 1 and events[0]["occurrence_count"] >= 12
    assert len([i for i in issues if i.get("rule") == "expansion"]) <= 5
    assert len(issues) < 20 * 12
    assert tree.find(exp.Select)


@pytest.mark.parametrize("empty", [True, False])
def test_authored_temporal_predicates_and_grain_are_preserved(tmp_path, empty):
    root = synthetic_project(tmp_path)
    p = project(root)
    resource = p.find_model("temporal")
    changes, skipped = optimize(p, select=["temporal"])
    assert not skipped
    candidate = changes.after[resource.path].decode()
    with duckdb.connect() as con:
        load_relations(con, empty=empty)
        for name in ("events", "requests", "findings"):
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM raw_{name}")
        before = parse_model(p, resource.code, expand=True)
        after = parse_model(p, candidate, expand=True)
        assert observe(con, executable(before.tree, before)) == observe(con, executable(after.tree, after))
        if not empty:
            assert observe(con, executable(after.tree, after))[2] == Counter([(1,2),(2,0),(3,0),(4,0)])


def test_relation_modifier_blocks_only_its_expansion(tmp_path):
    root = synthetic_project(tmp_path)
    put(root, "models/sampled.sql", "SELECT id, 1+2 AS k FROM {{ ref('events') }} TABLESAMPLE BERNOULLI (10 PERCENT)")
    tree, parsed, issues = inspect(project(root), "sampled", compiled=False)
    assert tree.selects[1].unalias() == exp.Literal.number(3)
    assert tree.find(exp.TableSample)
    assert any(i["rule"] == "expansion" and i["reason_code"] == "relation_modifiers" for i in issues)
    assert any(t.name in parsed.refs for t in tree.find_all(exp.Table))
