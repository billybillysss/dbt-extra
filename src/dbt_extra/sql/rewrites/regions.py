"""Scope-local structural rules; unsupported siblings are not rule inputs."""

from sqlglot import exp
from sqlglot.optimizer.eliminate_joins import eliminate_joins
from sqlglot.optimizer.scope import Scope, traverse_scope

from dbt_extra.sql.rewrites.structural import plain_joins, plain_queries
from dbt_extra.sql.safety import discardable, movable
from dbt_extra.sql.rewrites.expressions import predicate_simplification_safe
from dbt_extra.sql.rewrites.session import Eligibility, RejectedCandidate
from dbt_extra.sql.functions import has_generators


def movement_eligibility(tree):
    if any(n.alias_column_names for n in tree.find_all(exp.CTE, exp.Table, exp.Subquery)):
        return Eligibility(False, "positional_binding", "explicit relation column aliases must retain their bindings")
    if not plain_queries(tree) or not plain_joins(tree):
        if any(s.args.get("group") or any(isinstance(n, exp.AggFunc)
                   for p in s.selects for n in p.walk(prune=lambda n: isinstance(n, (exp.Window, exp.Subquery))))
               for s in tree.find_all(exp.Select)):
            return Eligibility(False, "aggregate_boundary", "aggregate boundary; cardinality/evaluation movement unproven")
        if tree.find(exp.Window, exp.Qualify):
            return Eligibility(False, "window_boundary", "window/QUALIFY boundary; evaluation and ordering movement unproven")
        return Eligibility(False, "scope_boundary", "window, set, outer join, correlation, modifier or row-limit boundary")
    if not movable(tree) or not predicate_simplification_safe(tree):
        return Eligibility(False, "evaluation_boundary", "unknown, volatile or potentially fallible evaluation must not move")
    if any(isinstance(n.this, exp.Literal) for n in tree.find_all(exp.Ordered)):
        return Eligibility(False, "positional_binding", "positional ordering must retain its bindings")
    return Eligibility()


def apply_to_regions(checkpoints, rule, function):
    # Select stable paths afresh for each rule; never reuse Scope objects from a
    # previous generation. Largest eligible disjoint regions run first.
    queries = list(checkpoints.tree.find_all(exp.Select))
    selected, attempts = [], []
    for index, query in enumerate(queries):
        if any(any(query is n for n in q.walk()) for q in selected):
            continue
        decision = movement_eligibility(query)
        if decision.eligible:
            selected.append(query)
        scope = f"select:{index}"
        # A metadata label survives copying, but is not a cached binding.
        query.meta["extra_rule_scope"] = scope
        attempts.append((scope, decision))
    for scope, decision in attempts:
        def apply(candidate, label=scope):
            target = next(q for q in candidate.find_all(exp.Select) if q.meta.get("extra_rule_scope") == label)
            replacement = function(target.copy())
            if rule in {"predicate_normalization", "predicate_pushdown", "join_reordering"}:
                if not _predicate_atoms(target) <= _predicate_atoms(replacement):
                    raise RejectedCandidate("predicate evaluation would be erased without a type/totality proof")
            if target is candidate:
                return replacement
            target.replace(replacement)
            return candidate

        checkpoints.attempt(rule, apply, decision=decision, scope=scope, requires=("bindings",))


def _predicate_atoms(tree):
    # Third-party predicate rules may call unrestricted simplify internally.
    # Even `TRUE OR varchar_column > 0` can raise during warehouse binding. Keep
    # every input-dependent atomic comparison unless separately proven total.
    # Qualifier changes are allowed when moving a bound predicate into its source.
    return {node.transform(lambda n: exp.column(n.name, quoted=n.this.args.get("quoted", False))
                           if isinstance(n, exp.Column) else n).sql()
            for node in tree.find_all(exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Is)
            if node.find(exp.Column)}


def _same_origin_matches(join):
    """Do not erase potentially fallible implicit coercions in ON comparisons.

    With no warehouse types, only equality of the same underlying column has a
    same-type proof. Follow plain SQL projections, never names/grain/dbt tests.
    """
    query = join.find_ancestor(exp.Select)
    if query is None:
        return False
    scopes = {id(scope.expression): scope for scope in traverse_scope(query)}

    def origin(column, scope, active=()):
        key = (id(scope), column.table, column.name)
        if key in active:
            return None
        source = scope.sources.get(column.table)
        if isinstance(source, exp.Table) and isinstance(source.this, exp.Identifier):
            return source.catalog, source.db, source.name, column.name
        if isinstance(source, Scope) and isinstance(source.expression, exp.Select):
            projections = [p.unalias() for p in source.expression.selects if p.output_name == column.name]
            if len(projections) == 1 and isinstance(projections[0], exp.Column):
                return origin(projections[0], source, (*active, key))
        return None

    def safe(node):
        if isinstance(node, exp.Boolean):
            return True
        if isinstance(node, (exp.Paren, exp.Not)):
            return safe(node.this)
        if isinstance(node, (exp.And, exp.Or)):
            return safe(node.this) and safe(node.expression)
        if isinstance(node, exp.EQ) and isinstance(node.this, exp.Column) and isinstance(node.expression, exp.Column):
            scope = scopes.get(id(query))
            left = origin(node.this, scope) if scope else None
            return left is not None and left == origin(node.expression, scope)
        return False

    on = join.args.get("on")
    return on is None or safe(on)


def join_eligibility(join, dialect):
    if join.side != "LEFT":
        return Eligibility(False, "join_kind_boundary", "only proven cardinality-preserving LEFT joins are eligible")
    if not isinstance(join.this, exp.Subquery):
        return Eligibility(False, "rhs_uniqueness_unproven", "RHS uniqueness is not proven from eligible SQL")
    if (not predicate_simplification_safe(join)
            or (join.args.get("on") is not None and not movable(join.args["on"]))):
        return Eligibility(False, "evaluation_boundary", "join evaluation may be fallible, volatile or opaque")
    if not _same_origin_matches(join):
        return Eligibility(False, "evaluation_boundary", "matching comparison types/coercions are not proven harmless")
    rhs = join.this.this
    if not isinstance(rhs, exp.Select) or rhs.find(exp.Window, exp.Limit, exp.Offset, exp.Subquery):
        return Eligibility(False, "scope_boundary", "RHS window, subquery or row-limit boundary")
    if (has_generators(rhs) or any(not discardable(p, dialect) for p in rhs.selects)
            or any(not isinstance(t.this, exp.Identifier) for t in rhs.find_all(exp.Table))
            or not predicate_simplification_safe(rhs)):
        return Eligibility(False, "evaluation_boundary", "RHS evaluation may be fallible, volatile or opaque")
    # Removing an unused relation must not erase fallible implicit comparisons
    # in its filters. Unknown input types are not a totality proof.
    if rhs.find(exp.Where, exp.Having):
        return Eligibility(False, "evaluation_boundary", "RHS filter evaluation is not proven harmless")
    group = rhs.args.get("group")
    if group and any(v for k, v in group.args.items() if k != "expressions"):
        return Eligibility(False, "grouping_boundary", "RHS grouping modifiers do not establish ordinary key uniqueness")
    return Eligibility()


def eliminate_safe_joins(tree, dialect):
    """Use SQLGlot cardinality proofs, but never erase observable RHS evaluation.

    LEFT joins only. No external uniqueness assumptions, grouping sets, custom
    aggregates, generators or potentially fallible outputs authorize removal.
    """
    for query in list(tree.find_all(exp.Select)):
        for join in list(query.args.get("joins") or []):
            if not join_eligibility(join, dialect).eligible:
                continue
            # Isolate a single attempted join. The library considers references
            # from every clause of this SELECT, including other joins.
            probe = query.copy()
            joins = probe.args.get("joins") or []
            for other in joins:
                if other != join:
                    other.set("side", "FULL")  # in the proof copy only
            eliminate_joins(probe)
            if len(probe.args.get("joins") or []) < len(query.args.get("joins") or []):
                query.set("joins", [j for j in query.args["joins"] if j is not join])
    return tree

