"""Workflow reports are explicit and independent of generic checked writes."""

from dbt_extra.files.changes import ChangeSet
from dbt_extra.optimization import optimize
from dbt_extra.workflow_results import WorkflowChanges
from tests.helpers import project


def test_workflow_report_fields_are_per_instance(native):
    first, second = WorkflowChanges(native), WorkflowChanges(native)
    first.optimization_report["example"] = {}
    first.metadata_skipped["example"] = "missing entry"
    assert second.optimization_report == {} and second.metadata_skipped == {}
    generic = ChangeSet(native)
    assert not hasattr(generic, "optimization_report")
    assert not hasattr(generic, "metadata_skipped")
    assert not hasattr(generic, "properties") and not hasattr(generic, "project_config")


def test_optimization_returns_explicit_workflow_changes(native):
    changes, skipped = optimize(project(native), select=["revenue"])
    assert isinstance(changes, WorkflowChanges) and not skipped
    report = changes.optimization_report["model.shop.revenue"]
    assert {"status", "changed", "formatting_only", "retained", "outcomes"} == report.keys()
