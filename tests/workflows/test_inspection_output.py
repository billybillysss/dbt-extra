"""Inspection keeps the default explanation concise without losing diagnostics."""

from copy import deepcopy

import pytest

from dbt_extra.cli import inspection_diagnostics
from dbt_extra.inspection import inspect
from dbt_extra.sql.rewrites.session import outcome_text
from tests.helpers import invoke, project, put, snapshot


@pytest.mark.parametrize("view", ["sql", "plan"])
@pytest.mark.parametrize("compiled", ["true", "false"])
def test_inspection_verbose_changes_only_diagnostics(native, view, compiled):
    put(native, "models/slv/orders.sql",
        "select id, trim(amount) as amount from {{ source('raw', 'orders') }}")
    before = snapshot(native)
    arguments = ("inspect", "revenue", "--columns", "revenue", "--view", view, "--compile", compiled)
    concise = invoke(native, *arguments)
    verbose = invoke(native, *arguments, "--verbose")
    assert concise.exit_code == verbose.exit_code == 0, (concise.output, verbose.output)
    assert "-- Source boundary: source.shop.raw.orders." in concise.output
    assert "-- Rewrites skipped:" in concise.output
    assert "-- Use --verbose" in concise.output
    assert "[select:" not in concise.output
    reason = "unknown, volatile or potentially fallible evaluation must not move"
    assert concise.output.count(reason) == 1
    assert verbose.output.count(reason) > 1
    assert "[select:" in verbose.output
    assert "(2 occurrences)" in verbose.output
    for result in (concise, verbose):
        assert "not stored-relation equivalence or a warehouse execution plan" in result.output
        assert "Not executed. Authored files unchanged." in result.output
    assert [line for line in concise.output.splitlines() if not line.startswith("--")] == [
        line for line in verbose.output.splitlines() if not line.startswith("--")]
    _, _, issues = inspect(project(native), "revenue", ["revenue"], compiled=compiled == "true")
    for issue in issues:
        if issue["status"] != "not_applicable":
            assert f"-- Boundary/coverage: {issue['resource_id']}: {outcome_text(issue)}" in verbose.output
    assert snapshot(native) == before


def test_summary_preserves_distinct_resources_reasons_and_rollbacks():
    def outcome(rule, status, reason, resource="model.shop.target", scope="select:0"):
        return dict(resource_id=resource, rule=rule, scope=scope, status=status,
                    reason_code=status, reason=reason, occurrence_count=2)

    issues = [
        outcome("predicate_pushdown", "blocked", "movement unproven"),
        outcome("subquery_merge", "blocked", "movement unproven", scope="select:1"),
        outcome("cte_cleanup", "blocked", "removal unproven"),
        outcome("predicate_pushdown", "blocked", "movement unproven", resource="model.shop.other"),
        outcome("subquery_merge", "rolled_back", "candidate\nrejected"),
        outcome("qualification", "applied", "validated"),
        outcome("qualification", "applied", "validated", scope="select:1"),
        outcome("projection_pruning", "not_applicable", "no change"),
        outcome("relation_resolution", "blocked", "Physical relation unavailable"),
        outcome("expansion", "blocked", "explicit boundary"),
        dict(resource_id="model.shop.legacy", reason="legacy warning"),
    ]
    original = deepcopy(issues)
    lines = list(inspection_diagnostics(issues))
    assert lines == [
        "-- Rewrites skipped: model.shop.target: movement unproven",
        "-- Rewrites skipped: model.shop.target: removal unproven",
        "-- Rewrites skipped: model.shop.other: movement unproven",
        "-- Rewrite rolled back: model.shop.target: candidate rejected",
        "-- Boundary/coverage: model.shop.target: Physical relation unavailable",
        "-- Boundary/coverage: model.shop.target: explicit boundary",
        "-- Boundary/coverage: model.shop.legacy: legacy warning",
        "-- Applied: model.shop.target: qualification.",
        "-- Use --verbose for per-rule/per-scope diagnostics.",
    ]
    assert issues == original
    assert list(inspection_diagnostics([])) == []


def test_unoptimized_inspection_keeps_boundaries_without_rewrite_hint(native):
    result = invoke(native, "inspect", "revenue", "--optimize", "false")
    assert result.exit_code == 0, result.output
    assert "-- Source boundary:" in result.output
    assert "-- Use --verbose" not in result.output


def test_inspection_help_documents_verbose(native):
    result = invoke(native, "inspect", "--help")
    assert result.exit_code == 0, result.output
    assert "--verbose" in result.output
