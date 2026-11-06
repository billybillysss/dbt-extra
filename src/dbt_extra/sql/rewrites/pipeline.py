"""Explicit rule ordering and policy for source and inspection workflows."""

from sqlglot import exp
from sqlglot.optimizer.eliminate_ctes import eliminate_ctes
from sqlglot.optimizer.merge_subqueries import merge_subqueries

from dbt_extra.sql.rewrites.expressions import simplify_source_expressions
from dbt_extra.sql.rewrites.regions import apply_to_regions, eliminate_safe_joins, join_eligibility
from dbt_extra.sql.rewrites.session import Checkpoints, Eligibility, validate_contract
from dbt_extra.sql.rewrites.structural import (
    deduplicate_subqueries, normalize_predicates, optimize_safe_joins, pushdown_safe_predicates,
)
from dbt_extra.sql.safety import movable


def apply_structural_rules(checkpoints, dialect, *, inspection=False):
    apply_to_regions(checkpoints, "predicate_normalization", normalize_predicates)
    apply_to_regions(checkpoints, "predicate_pushdown", lambda t: pushdown_safe_predicates(t, dialect=dialect))
    apply_to_regions(checkpoints, "subquery_merge", merge_subqueries)
    apply_to_regions(checkpoints, "join_reordering", optimize_safe_joins)
    checkpoints.attempt("subquery_deduplication", deduplicate_subqueries,
                        decision=Eligibility(not any(isinstance(n, exp.Anonymous) for n in checkpoints.tree.walk()),
                                             "opaque_function", "opaque functions cannot be factored"), requires=("bindings",))
    if inspection:
        checkpoints.attempt("join_elimination", lambda t: eliminate_safe_joins(t, dialect), requires=("bindings",))
        for index, join in enumerate(checkpoints.tree.find_all(exp.Join)):
            decision = join_eligibility(join, dialect)
            code, reason = decision.reason_code, decision.reason
            if decision.eligible:
                code, reason = "rhs_uniqueness_unproven", "RHS uniqueness and harmless matching conditions are not proven"
            checkpoints.outcomes.add("join_elimination", f"join:{index}", "blocked", code, reason)
    checkpoints.attempt("cte_cleanup", eliminate_ctes,
                        decision=Eligibility(movable(checkpoints.tree), "evaluation_boundary", "CTE evaluation is not proven removable"),
                        requires=("bindings",))
    apply_to_regions(checkpoints, "subquery_merge", merge_subqueries)


def rewrite_source(tree, dialect, *, outcomes=None, validate=None):
    original = tree.copy()

    def checked(candidate):
        validate_contract(original, candidate, dialect)
        if validate:
            validate(candidate)

    checkpoints = Checkpoints(tree, dialect, outcomes, validate=checked)
    checkpoints.capabilities.add("bindings")
    checkpoints.attempt("literal_simplification", lambda t: simplify_source_expressions(t, dialect))
    apply_structural_rules(checkpoints, dialect)
    return checkpoints.tree
