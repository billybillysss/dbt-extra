"""Read-only explanations of dbt model definitions across upstream boundaries."""

import re

from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

from dbt_extra.errors import SpecError
from dbt_extra.analysis.expansion import ModelExpansion
from dbt_extra.sql.models import ParsedSQL
from dbt_extra.sql.rewrites.pipeline import apply_structural_rules
from dbt_extra.sql.rewrites.projections import prune_projections
from dbt_extra.project.relations import resolve_physical_relations
from dbt_extra.sql.renderer import sql
from dbt_extra.sql.qualification import qualify_source
from dbt_extra.sql.rewrites.expressions import simplify_source_expressions
from dbt_extra.sql.rewrites.session import Checkpoints, Outcomes, RejectedCandidate, validate_contract
from dbt_extra.sql.aliases import available_alias
from dbt_extra.sql.rewrites.query_boundaries import simplify_query_boundaries


def inspect(project, name, columns=None, *, boundaries=(), expanded=True, optimized=True, compiled=True):
    dialect = project.require_dialect()
    resource = project.find_model(name)
    boundary_ids = {project.find_model(n).id for n in boundaries}
    issues = []
    outcomes = Outcomes(resource.id, issues)
    expansion = ModelExpansion(project, outcomes, boundaries=boundary_ids, expanded=expanded)
    expansion.validate_boundaries(resource)
    complete = expansion.expand(resource, wanted=columns if optimized else None)
    evidence, refs, macros = expansion.evidence, expansion.refs, expansion.macros
    normalize_identifiers(complete, dialect=dialect)
    if any(p.is_star for p in complete.selects):
        schemas = evidence.for_parsed(ParsedSQL(complete, refs))
        try:
            resolved = qualify_source(complete.copy(), schemas, dialect)
            if not any(p.is_star for p in resolved.selects):
                complete = resolved
        except (SpecError, SqlglotError, ValueError) as exc:
            outcomes.add("wildcard_expansion", "query", "blocked", "incomplete_schema",
                         f"Wildcard expansion unavailable: {exc}")
    if columns:
        if any(p.is_star for p in complete.selects):
            raise SpecError("Selected-column inspection requires known output columns; root SELECT * is unresolved")
        outputs, selected = [p.output_name for p in complete.selects], []
        for column in dict.fromkeys(columns):
            matching = [o for o in outputs if o == column]
            if not matching:
                normalized = normalize_identifiers(exp.to_identifier(column), dialect=dialect).name
                matching = [o for o in outputs if o == normalized]
            if len(matching) != 1:
                raise SpecError(f"Unknown or ambiguous output column: {column}")
            selected.append((column, matching[0]))
        occupied = {i.name for i in complete.find_all(exp.Identifier)}
        alias = available_alias(resource.name, occupied)
        tree = exp.select(*(exp.alias_(exp.column(actual, table=alias, quoted=True), requested, quoted=True)
                            for requested, actual in selected)).from_(complete.subquery(exp.to_identifier(alias, quoted=True)))
    else:
        tree = complete
    if optimized:
        inputs = evidence.for_parsed(ParsedSQL(tree, refs))
        original = tree.copy()

        def validate(candidate):
            validate_contract(original, candidate, dialect)
            if "bindings" in checkpoints.capabilities:
                try:
                    qualify_source(candidate, inputs, dialect)
                except SpecError as exc:
                    raise RejectedCandidate(str(exc)) from exc

        checkpoints = Checkpoints(tree, dialect, outcomes, validate=validate)
        checkpoints.attempt("literal_simplification", lambda t: simplify_source_expressions(t, dialect))

        def bind(candidate):
            try:
                return qualify_source(candidate, inputs, dialect)
            except SpecError as exc:
                raise RejectedCandidate(str(exc)) from exc

        checkpoints.attempt("qualification", bind, provides=("bindings",))
        checkpoints.attempt("projection_pruning", lambda t: prune_projections(t, dialect=dialect), requires=("bindings",))
        apply_structural_rules(checkpoints, dialect, inspection=True)
        checkpoints.attempt("query_boundary_simplification", lambda t: simplify_query_boundaries(t, dialect), requires=("bindings",))
        checkpoints.attempt("literal_simplification", lambda t: simplify_source_expressions(t, dialect))
        tree = checkpoints.tree
        validate(tree)
    if compiled:
        refs, compilation_issues = resolve_physical_relations(project, tree, refs)
        for item in compilation_issues:
            outcomes.add("relation_resolution", "resource", "blocked", "relation_unavailable", item["reason"],
                         resource=item["resource_id"])
    return tree, ParsedSQL(tree, refs, macros=macros), issues


def plan(tree, parsed, dialect):
    lines = ["Logical plan (not a warehouse execution plan)"]
    for index, query in enumerate((q for q in tree.walk() if isinstance(q, exp.Query) and not isinstance(q, exp.Subquery)), 1):
        lines.append(f"\nq{index}: {query.key.upper()}")
        for key in ("expressions", "from_", "joins", "where", "group", "having", "qualify", "order", "limit", "distinct"):
            value = query.args.get(key)
            if value:
                values = value if isinstance(value, list) else [value]
                lines.append(f"  {key.rstrip('_')}: " + ", ".join(sql(v, dialect) for v in values))
    text = "\n".join(lines)
    for token, ref in parsed.refs.items():
        text = text.replace(token, ref.text)
    for token, raw in parsed.macros.items():
        text = re.sub(re.escape(token) + r"\(\)", lambda _: raw, text, flags=re.IGNORECASE)
    return text
