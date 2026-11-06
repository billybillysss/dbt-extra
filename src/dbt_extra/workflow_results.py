"""Explicit reports attached to checked workflow changes, not generic file writes."""

from typing import Literal, TypedDict

from dbt_extra.files.changes import ChangeSet


class RuleOutcome(TypedDict):
    rule: str
    resource_id: str
    scope: str
    status: str
    reason_code: str
    reason: str
    occurrence_count: int


class OptimizationReport(TypedDict):
    status: Literal["unchanged", "formatted", "qualified", "rewritten"]
    formatting_only: bool
    changed: bool
    retained: list[str]
    outcomes: list[RuleOutcome]


class WorkflowChanges(ChangeSet):
    def __init__(self, root):
        super().__init__(root)
        self.optimization_report: dict[str, OptimizationReport] = {}
        self.metadata_skipped: dict[str, str] = {}
