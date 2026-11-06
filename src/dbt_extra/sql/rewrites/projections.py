"""Safety-root adapter for SQLGlot's all-consumer projection dependency analysis.

Only projection lists are changed. No join, predicate, aggregate or template is
moved. Synthetic ORDER references exist solely in the analysis copy: they make
observable evaluations and authored alias bindings roots of the dependency graph.
"""

from sqlglot import exp
from sqlglot.optimizer.pushdown_projections import projection_reachability

from dbt_extra.sql.safety import discardable


def prune_source_projections(authored, expanded, qualified, *, dialect=None):
    """Delete proven-dead authored projections without moving or inlining macros."""
    result = authored.copy()
    queries = list(result.find_all(exp.Select))
    expanded_queries = list(expanded.find_all(exp.Select))
    bound = qualified.copy()
    bound_queries = list(bound.find_all(exp.Select))
    if not (len(queries) == len(expanded_queries) == len(bound_queries)):
        return result
    if any(len(a.selects) != len(b.selects) or len(a.selects) != len(c.selects)
           or any(p.is_star for p in a.selects)
           for a, b, c in zip(queries, expanded_queries, bound_queries)):
        return result
    if any(node.alias_column_names for node in authored.find_all(exp.CTE, exp.Table, exp.Subquery)):
        return result
    originals = {}
    for index, (query, source) in enumerate(zip(bound_queries, queries)):
        query.meta["extra_projection_scope"] = index
        for position, projection in enumerate(query.selects):
            projection.meta["extra_projection_position"] = position
        originals[index] = list(source.selects)
    prune_projections(bound, authored=authored, dialect=dialect)
    for query in bound_queries:
        index = query.meta["extra_projection_scope"]
        queries[index].set("expressions", [originals[index][p.meta["extra_projection_position"]]
                                           for p in query.selects])
    return result


def prune_projections(tree, *, authored=None, dialect=None):
    analysis = tree.copy()
    queries = list(analysis.find_all(exp.Select))
    sources = list((authored or tree).find_all(exp.Select))
    if len(queries) != len(sources):
        return tree
    for query, source in zip(queries, sources):
        if len(query.selects) != len(source.selects) or any(p.is_star or not p.output_name for p in query.selects):
            return tree
        names = {p.output_name for p in query.selects}
        # Include QUALIFY/HAVING and original lateral aliases. SQLGlot versions
        # differ in whether those dependencies survive qualification.
        aliases = {c.name.casefold() for key, clause in source.args.items()
                   if key not in {"expressions", "with_", "from_", "joins"}
                   for item in (clause if isinstance(clause, list) else [clause])
                   if isinstance(item, exp.Expression)
                   for c in item.find_all(exp.Column) if not c.table}
        for projection in source.selects:
            if not isinstance(projection.unalias(), exp.Column):
                aliases.update(c.name.casefold() for c in projection.find_all(exp.Column) if not c.table)
        keep = [p.output_name for p, original in zip(query.selects, source.selects)
                 if not discardable(p, dialect) or not discardable(original, dialect) or original.output_name.casefold() in aliases]
        keep += [c.name for key in ("qualify", "having") if query.args.get(key)
                 for c in query.args[key].find_all(exp.Column) if not c.table and c.name in names]
        clauses = [source.args.get(k) for k in ("group", "order")]
        prefix = max((int(n.this) for clause in clauses if clause
                      for n in clause.find_all(exp.Literal) if n.is_int), default=0)
        if any(clause and any(v.name.upper() == "ALL" for v in clause.find_all(exp.Var)) for clause in clauses):
            prefix = len(query.selects)
        keep += [p.output_name for p in query.selects[:prefix]]
        if keep:
            order = query.args.get("order")
            items = list(order.expressions) if order else []
            query.set("order", exp.Order(expressions=[*items, *(exp.Ordered(this=exp.column(n)) for n in keep)]))
    # SQLGlot conservatively roots Anonymous calls as possible set-returning
    # functions. Expose only certified, discardable null checks as scalar in
    # this dependency-analysis copy; authored function nodes are never replaced.
    null_checks = [node for node in analysis.find_all(exp.Anonymous) if discardable(node, dialect)]
    for node in reversed(null_checks):
        check = exp.Is(this=node.expressions[0].copy(), expression=exp.Null())
        node.replace(exp.Not(this=check) if node.name.lower() == "isnotnull" else check)
    reach = projection_reachability(analysis, whole_query=True)
    positions = {id(q): i for i, q in enumerate(queries)}
    targets = list(tree.find_all(exp.Select))
    for scope in reach.scopes:
        query = scope.expression
        if not isinstance(query, exp.Select) or not reach.live[scope]:
            continue
        target = targets[positions[id(query)]]
        roots = reach.selections[scope]
        # Keep a prefix for positional clauses. This avoids rewriting authored
        # ordinals, and supports grouping sets without rebinding their positions.
        group = target.args.get("group")
        ordinals = [int(n.this) for n in group.find_all(exp.Literal) if n.is_int] if group else []
        prefix = max(ordinals, default=0)
        kept = [p for i, (p, live) in enumerate(zip(target.selects, roots)) if live or i < prefix]
        if kept:
            target.set("expressions", kept)
    return tree
