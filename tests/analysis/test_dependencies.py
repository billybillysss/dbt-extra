"""Graph validation and result coverage contracts."""

import pytest

from dbt_extra import SpecError
from dbt_extra.analysis.dependencies import validate_cycles
from dbt_extra.analysis.models import coverage


def test_diamond_graph_and_external_boundaries_are_not_cycles():
    validate_cycles({"report": ["left", "right"], "left": ["source"], "right": ["source"]})


def test_cycle_error_includes_the_dependency_chain():
    with pytest.raises(SpecError, match="report -> orders -> report"):
        validate_cycles({"report": ["orders"], "orders": ["report"]})


def test_coverage_counts_explicit_statuses():
    assert coverage([{"status": "parsed"}, {"status": "unavailable"}, {"status": "parsed"}]) == {"parsed": 2, "unavailable": 1}
