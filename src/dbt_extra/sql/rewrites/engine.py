"""Project-independent authored-SQL passes, validation and bounded convergence."""

from collections import Counter

from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import traverse_scope

from dbt_extra.errors import SpecError
from dbt_extra.sql.dialects import validate_dialect
from dbt_extra.sql.templates.macros import macro_calls
from dbt_extra.sql.parser import parse_authored
from dbt_extra.sql.qualification import qualify_source, remember_schema_outputs, source_schema
from dbt_extra.sql.renderer import render, sql
from dbt_extra.sql.rewrites.expressions import simplify_source_expressions
from dbt_extra.sql.rewrites.session import Checkpoints, Outcomes, RejectedCandidate, validate_contract
from dbt_extra.sql.rewrites.structural import collapse_complementary_union, decorrelate_filter_exists
from dbt_extra.sql.rewrites.pipeline import rewrite_source
from dbt_extra.sql.rewrites.projections import prune_source_projections
from dbt_extra.sql.aliases import generated_aliases, redundant_aliases
from dbt_extra.sql.identifiers import remember_identifiers, remember_outputs, restore_identifiers


def _optimizer_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (SqlglotError, KeyError) as exc:
        raise SpecError(f"Cannot safely optimize ({type(exc).__name__}: {exc}); verify complete input schemas and SQLGlot compatibility") from exc


def _once(code, dialect, *, schema, pretty, parse=None, parse_expanded=None, schema_for=None,
          report=None, expand=False, terminate=True):
    parse = parse or (lambda text: parse_authored(text, dialect))
    parse_expanded = parse_expanded or parse
    parsed = parse(code)
    if parsed.template_source is not None and not expand:
        Outcomes(values=report.setdefault("outcomes", []) if report is not None else None).add(
            "static_jinja", "template", "blocked", "authored_template_boundary",
            "static analysis available; original template retained (use explicit expand to render SQL)")
        return code
    expanded = parse_expanded(code) if parsed.macros else parsed
    outcomes = Outcomes(values=report.setdefault("outcomes", []) if report is not None else None)
    inputs = schema_for(expanded) if schema_for else schema
    inputs = _optimizer_call(source_schema, inputs, dialect)
    tree = expanded.tree.copy()
    if not parsed.macros:
        early = Checkpoints(tree, dialect, outcomes, validate=lambda t: validate_contract(parsed.tree, t, dialect))
        early.attempt("exists_decorrelation", lambda t: decorrelate_filter_exists(t, dialect=dialect, schema=inputs))
        early.attempt("complementary_union", collapse_complementary_union)
        tree = early.tree
        if report is not None and tree != parsed.tree:
            report["rewritten"] = True
    remember_identifiers(tree)
    occupied = {i.name.casefold() for i in tree.find_all(exp.Identifier)}
    for node in tree.find_all(exp.Table, exp.Subquery):
        node.meta["extra_explicit_alias"] = bool(node.args.get("alias"))
    prepared = tree.copy()
    checkpoints = Checkpoints(tree, dialect, outcomes)

    def bind(candidate):
        try:
            return qualify_source(candidate, inputs, dialect)
        except SpecError as exc:
            raise RejectedCandidate(str(exc)) from exc

    bound = checkpoints.attempt("qualification", bind, provides=("bindings",))
    qualified = checkpoints.tree
    if bound:
        remember_schema_outputs(qualified, inputs)
        remember_outputs(qualified)
    unnamed = any(not p.output_name and not p.is_star
                   for scope in traverse_scope(tree) for p in scope.expression.selects)
    if not bound:
        local = Checkpoints(parsed.tree.copy() if parsed.macros else prepared, dialect, outcomes,
                            validate=lambda t: validate_contract(parsed.tree, t, dialect))
        local.attempt("literal_simplification", lambda t: simplify_source_expressions(t, dialect, macros=parsed.macros))
        for rule in ("projection_pruning", "predicate_pushdown", "join_reordering"):
            local.attempt(rule, lambda t: t, requires=("bindings",))
        result = local.tree
        if report is not None and result != parsed.tree:
            report["rewritten"] = True
    elif unnamed:
        # Keep authored unnamed expressions, not SQLGlot's synthetic labels.
        # An unnamed aggregate in a nested query need not block outer pruning.
        local = Checkpoints(parsed.tree.copy() if parsed.macros else prepared, dialect, outcomes,
                            validate=lambda t: validate_contract(parsed.tree, t, dialect))
        local.attempt("projection_pruning", lambda t: prune_source_projections(t, expanded.tree, qualified, dialect=dialect))
        local.attempt("literal_simplification", lambda t: simplify_source_expressions(t, dialect, macros=parsed.macros))
        result = local.tree
        if report is not None and result != parsed.tree:
            report["rewritten"] = True
    elif parsed.macros:
        local = Checkpoints(parsed.tree.copy(), dialect, outcomes,
                            validate=lambda t: validate_contract(parsed.tree, t, dialect))
        local.capabilities.add("bindings")
        local.attempt("projection_pruning", lambda t: prune_source_projections(t, expanded.tree, qualified, dialect=dialect), requires=("bindings",))
        local.attempt("literal_simplification", lambda t: simplify_source_expressions(t, dialect, macros=parsed.macros))
        result = local.tree
        if report is not None and result != parsed.tree:
            report["rewritten"] = True
    else:
        interface = [p.output_name for p in qualified.selects]
        spelled_interface = [p.output_name for p in restore_identifiers(qualified.copy()).selects]
        original = qualified.copy()

        def validate(candidate):
            validate_contract(original, candidate, dialect)
            bind(candidate)  # rebuild bindings; never reuse stale Scope objects

        local = Checkpoints(qualified, dialect, outcomes, validate=validate)
        local.capabilities.add("bindings")

        def prune(candidate):
            pruned = prune_source_projections(prepared, prepared, candidate, dialect=dialect)
            if pruned == prepared:
                return candidate
            result = bind(pruned)
            remember_schema_outputs(result, inputs)
            remember_outputs(result)
            return result

        local.attempt("projection_pruning", prune, requires=("bindings",))
        local.attempt("literal_simplification", lambda t: simplify_source_expressions(t, dialect, schema=inputs))
        result = _optimizer_call(rewrite_source, local.tree, dialect, outcomes=outcomes, validate=validate)
        if report is not None and result != original:
            report["rewritten"] = True
        result = _optimizer_call(qualify_source, result, inputs, dialect)
        if [p.output_name for p in result.selects] != interface:
            raise SpecError("Optimization changed the output interface")
        result = redundant_aliases(restore_identifiers(generated_aliases(result, occupied)))
        if [p.output_name for p in result.selects] != spelled_interface:
            raise SpecError("Optimization changed output spelling or order")
    before_comments = sorted(c for n in parsed.tree.walk() for c in n.comments or [])
    after_comments = sorted(c for n in result.walk() for c in n.comments or [])
    if before_comments != after_comments:
        raise SpecError("Rewrite would discard SQL comments")
    candidate = render(result, parsed, dialect, pretty=pretty, prefix=True, format_config=True,
                       terminate=terminate)
    reparsed = parse(candidate)
    if reparsed.tree != result and sql(reparsed.tree, dialect) != sql(result, dialect):
        raise SpecError("Candidate SQL did not round-trip")
    if parsed.macros and bound:
        validated = _optimizer_call(qualify_source, parse_expanded(candidate).tree, inputs, dialect)
        if [p.output_name for p in validated.selects] != [p.output_name for p in qualified.selects]:
            raise SpecError("Optimization changed the output interface")
    elif bound:
        _optimizer_call(qualify_source, reparsed.tree, inputs, dialect)
    if not expand and Counter(raw for _, _, raw, _ in macro_calls(code)) != Counter(raw for _, _, raw, _ in macro_calls(candidate)):
        raise SpecError("Rewrite would change authored macro calls")
    return candidate


def rewrite_sql(code, dialect, *, schema=None, pretty=True, parse=None, parse_expanded=None,
                schema_for=None, report=None, expand=False, terminate=True):
    """Converge guarded passes using explicit parsing and schema providers."""
    seen = {code}
    for _ in range(4):
        candidate = _once(code, dialect, schema=schema, pretty=pretty, parse=parse,
                          parse_expanded=parse_expanded, schema_for=schema_for, report=report,
                          expand=expand, terminate=terminate)
        if candidate == code:
            return candidate
        if candidate in seen:
            raise SpecError("Source optimization entered a rewrite cycle; model unchanged")
        seen.add(candidate)
        code = candidate
    raise SpecError("Source optimization did not converge within four passes; model unchanged")


def optimize_source(code, dialect, *, schema=None, pretty=True, outcomes=None):
    """Rewrite only when bindings, interfaces and a bounded fixed point validate.

    Explicit caller schemas must be complete, ordered relation schemas, not a
    list of documented columns. No warehouse access or metadata guesses occur.
    """
    return rewrite_sql(code, validate_dialect(dialect), schema=schema, pretty=pretty,
                        report={"outcomes": outcomes} if outcomes is not None else None)
