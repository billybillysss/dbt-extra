"""Read-only explanations of dbt model definitions across upstream boundaries."""

import re

from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer import optimize
from sqlglot.optimizer.eliminate_ctes import eliminate_ctes
from sqlglot.optimizer.eliminate_joins import eliminate_joins
from sqlglot.optimizer.merge_subqueries import merge_subqueries
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.pushdown_projections import pushdown_projections
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope
from sqlglot.optimizer.simplify import simplify

from dbt_extra.errors import SpecError
from dbt_extra.sql.parser import Parsed
from dbt_extra.sql.macros import parse_model
from dbt_extra.sql.inspection_rules import (deduplicate_subqueries, normalize_predicates,
                                       optimize_safe_joins, pushdown_safe_predicates)
from dbt_extra.sql.references import resolve_ref
from dbt_extra.sql.relations import compile_relations
from dbt_extra.sql.renderer import sql
from dbt_extra.sql.qualification import INFER_SCHEMA_OPTIONS, bind_single_inputs
from dbt_extra.sql.scopes import volatile


def inspection_rules(tree):
    # Retain inner outputs for global aggregates: pruning the last aggregate
    # can change one row into zero/many rows, including on empty inputs.
    global_aggregate = any(isinstance(node, exp.Select) and not node.args.get("group")
                           and any(isinstance(p, exp.AggFunc) or p.find(exp.AggFunc) for p in node.selects)
                           for node in tree.walk())
    projections = () if global_aggregate else (pushdown_projections,)
    # Pruning exposes unused, cardinality-preserving joins. Remove their CTEs
    # before merging again so selected-output wrappers can also collapse.
    return (qualify, simplify, *projections, merge_subqueries,
            normalize_predicates, pushdown_safe_predicates, optimize_safe_joins,
            deduplicate_subqueries, eliminate_joins, eliminate_ctes, merge_subqueries, simplify)


def inspect(project, name, columns=None, *, boundaries=(), expanded=True, optimized=True, compiled=True):
    dialect = project.require_dialect()
    resource = project.find(name)
    boundary_ids = {project.find(n).id for n in boundaries}
    parsed_cache, refs, macros, issues = {}, {}, {}, []

    def parsed(r):
        if r.id not in parsed_cache:
            parsed_cache[r.id] = parse_model(project, r.code, r.id, expand=expanded)
        return parsed_cache[r.id]

    visited = set()

    def reachable(r):
        if r.id in visited:
            return
        visited.add(r.id)
        try:
            value = parsed(r)
        except SpecError:
            return
        for ref in value.refs.values():
            upstream = resolve_ref(project, ref)
            if upstream:
                reachable(upstream)

    reachable(resource)
    invalid = boundary_ids - (visited - {resource.id})
    if invalid:
        raise SpecError(f"--from models are not upstream dependencies: {', '.join(sorted(invalid))}")

    def expand(r, active=()):
        if r.id in active:
            raise SpecError(f"Cyclic SQL expansion: {' -> '.join((*active, r.id))}")
        value = parsed(r)
        refs.update(value.refs)
        macros.update(value.macros)
        tree = value.tree.copy()
        for scope in list(traverse_scope(tree)):
            for table in list(scope.tables):
                if isinstance(scope.sources.get(table.alias_or_name), Scope):
                    continue
                ref = value.refs.get(table.name)
                if not ref:
                    continue
                if ref.kind == "this":
                    table.meta["extra_owner"] = r.id
                upstream = resolve_ref(project, ref)
                reason, replacement = None, None
                if not expanded:
                    reason = "expansion disabled"
                elif upstream is None:
                    reason = "stored self relation" if ref.kind == "this" else "unresolved relation"
                elif upstream.id in boundary_ids:
                    reason = "explicit boundary"
                elif upstream.kind != "model" or (upstream.path and upstream.path.suffix == ".py"):
                    reason = upstream.kind + " input"
                elif upstream.path is None:
                    reason = "artifact/package-only definition; authored local source unavailable"
                else:
                    try:
                        up = parsed(upstream)
                        materialized = up.config.get("materialized", upstream.config.get("materialized", "view"))
                        if up.config_dynamic:
                            reason = "dynamic configuration; materialization cannot be established offline"
                        elif materialized not in {"view", "table", "ephemeral"}:
                            reason = f"{materialized} materialization"
                        elif volatile(up.tree):
                            reason = "volatile or unknown function"
                        else:
                            replacement = expand(upstream, (*active, r.id))
                    except SpecError as exc:
                        reason = str(exc)
                if replacement is None:
                    issues.append({"resource_id": upstream.id if upstream else ref.text, "reason": reason})
                    continue
                modifiers = {k for k, v in table.args.items() if v is not None} - {"this", "db", "catalog", "alias"}
                if modifiers:
                    raise SpecError(f"Cannot expand relation modifiers: {', '.join(sorted(modifiers))}")
                alias = table.args.get("alias") or exp.TableAlias(this=exp.to_identifier(table.name))
                table.replace(exp.Subquery(this=replacement, alias=alias.copy()))
        return tree

    complete = expand(resource)
    normalize_identifiers(complete, dialect=dialect)
    if any(p.is_star for p in complete.selects):
        schemas = {}
        for token, ref in refs.items():
            upstream = resolve_ref(project, ref)
            if upstream and upstream.known_columns:
                schemas[token] = {c: p.get("data_type") or "UNKNOWN" for c, p in upstream.known_columns.items()}
        try:
            resolved = qualify(complete.copy(), dialect=dialect, schema=schemas, validate_qualify_columns=True)
            if not any(p.is_star for p in resolved.selects):
                complete = resolved
        except (SqlglotError, ValueError) as exc:
            issues.append({"resource_id": resource.id, "reason": f"Wildcard expansion unavailable: {exc}"})
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
        alias = "extra_selected_output"
        occupied = {i.name for i in complete.find_all(exp.Identifier)}
        while alias in occupied:
            alias += "_"
        tree = exp.select(*(exp.alias_(exp.column(actual, table=alias, quoted=True), requested, quoted=True)
                            for requested, actual in selected)).from_(complete.subquery(exp.to_identifier(alias, quoted=True)))
    else:
        tree = complete
    if optimized and not volatile(tree):
        try:
            tree = optimize(bind_single_inputs(tree, {}, dialect), dialect=dialect, rules=inspection_rules(tree),
                            **INFER_SCHEMA_OPTIONS, validate_qualify_columns=True)
        except SqlglotError as exc:
            issues.append({"resource_id": resource.id, "reason": f"Simplification unavailable; complete query retained: {exc}"})
            tree = exp.select(*(exp.alias_(exp.column(actual, table=alias, quoted=True), requested, quoted=True)
                                for requested, actual in selected)).from_(complete.subquery(exp.to_identifier(alias, quoted=True))) if columns else complete
    if compiled:
        refs, compilation_issues = compile_relations(project, tree, refs)
        issues.extend(compilation_issues)
    return tree, Parsed(tree, refs, macros=macros), issues


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
