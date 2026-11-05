"""Small, guarded authored-SQL rule set. No join elimination or uniqueness guesses."""

from sqlglot import exp
from sqlglot.optimizer.eliminate_ctes import eliminate_ctes
from sqlglot.optimizer.merge_subqueries import merge_subqueries
from sqlglot.optimizer.pushdown_predicates import pushdown_predicates
from sqlglot.optimizer.pushdown_projections import pushdown_projections
from sqlglot.optimizer.scope import Scope, traverse_scope

from dbt_extra.sql.inspection_rules import (deduplicate_subqueries, normalize_predicates,
                                       optimize_safe_joins, plain_joins, plain_queries,
                                       pushdown_safe_predicates)
from dbt_extra.sql.source_expressions import predicate_simplification_safe, simplify_source_expressions


def remember_identifiers(tree):
    for identifier in tree.find_all(exp.Identifier):
        identifier.meta["extra_spelling"] = dict(identifier.args)


def remember_outputs(tree):
    # Qualification synthesizes aliases from normalized column names. Carry the
    # authored output spelling through later substitution (e.g. renamed CTEs).
    for alias in tree.find_all(exp.Alias):
        identifier = alias.args["alias"]
        if "extra_spelling" not in identifier.meta and isinstance(alias.this, exp.Column):
            spelling = alias.this.this.meta.get("extra_spelling")
            if spelling:
                identifier.meta["extra_spelling"] = spelling


def restore_identifiers(tree):
    for identifier in tree.find_all(exp.Identifier):
        spelling = identifier.meta.get("extra_spelling")
        if spelling:
            identifier.set("this", spelling["this"])
            identifier.set("quoted", spelling.get("quoted", False))
    return tree


def rewrite_source(tree, dialect):
    tree = simplify_source_expressions(tree, dialect)
    # Query-wide movement barriers deliberately trade opportunities for safety.
    # In particular, never prune COUNT(*)'s input cardinality or cross null extension,
    # windows, set operations, DISTINCT, positional dependencies or row limits.
    eligible = (plain_queries(tree) and plain_joins(tree)
                and not any(s.args.get("distinct") for s in tree.find_all(exp.Select))
                and not any(isinstance(n.this, exp.Literal) for n in tree.find_all(exp.Ordered)))
    if eligible:
        tree = pushdown_projections(tree)
        if predicate_simplification_safe(tree):
            tree = pushdown_predicates(tree, dialect=dialect)
        tree = merge_subqueries(tree)
        tree = eliminate_ctes(tree)
    # These rules have independent guards: DISTINCT can admit filter pushdown,
    # and repeated grouped inputs can be factored without flattening aggregates.
    if plain_queries(tree) and plain_joins(tree) and predicate_simplification_safe(tree):
        tree = normalize_predicates(tree)
    if predicate_simplification_safe(tree):
        tree = pushdown_safe_predicates(tree, dialect=dialect)
    tree = optimize_safe_joins(tree)
    tree = deduplicate_subqueries(tree)
    return tree


def collapse_complementary_union(tree):
    """Combine identical UNION ALL scans with complementary equality filters.

    SQL NULLs match neither = nor <>. Keep both comparisons (and their coercions),
    rather than inferring column types and replacing them with IS NOT NULL. Never
    collapse DISTINCT, limits, different projections, joins, or differing inputs.
    """
    for union in list(tree.find_all(exp.Union)):
        left, right = union.this, union.expression
        if (union.args.get("distinct") is not False
                or any(v is not None for k, v in union.args.items()
                       if k not in {"this", "expression", "distinct"})
                or not isinstance(left, exp.Select) or not isinstance(right, exp.Select)
                or not all(plain_queries(q) and plain_joins(q) for q in (left, right))
                or any(q.args.get(k) for q in (left, right)
                       for k in ("distinct", "order", "with_", "joins"))
                or any(n.comments for n in union.walk())
                or any(not isinstance(p.unalias(), exp.Column) for p in left.selects)):
            continue
        filters = [q.args.get("where") for q in (left, right)]
        if not all(filters):
            continue
        a, b = (f.this for f in filters)
        if isinstance(a, exp.NEQ) and isinstance(b, exp.EQ):
            a, b = b, a
        if (not isinstance(a, exp.EQ) or not isinstance(b, exp.NEQ)
                or not isinstance(a.this, exp.Column) or not isinstance(a.expression, exp.Literal)
                or a.this != b.this or a.expression != b.expression):
            continue
        templates = [q.copy() for q in (left, right)]
        for q in templates:
            q.set("where", None)
        if templates[0] != templates[1]:
            continue
        replacement = left.copy().where(exp.Or(this=a.copy(), expression=b.copy()), append=False)
        if union is tree:
            tree = replacement
        else:
            union.replace(replacement)
    return tree


def decorrelate_filter_exists(tree):
    """Positive WHERE EXISTS with one explicit equality becomes a set-membership filter.

    This is deliberately not general decorrelation. Only conjunctive WHERE terms,
    SELECT 1 over one plain table, and qualified inner-only residuals are accepted.
    FALSE and UNKNOWN both reject a row here; this is not valid in a SELECT or NOT.
    """
    for scope in list(traverse_scope(tree)):
        query = scope.expression
        where = query.args.get("where")
        if not isinstance(query, exp.Select) or not where:
            continue
        for term in list(where.this.flatten() if isinstance(where.this, exp.And) else [where.this]):
            if not isinstance(term, exp.Exists) or any(n.comments for n in term.walk()):
                continue
            inner = term.this
            if (not isinstance(inner, exp.Select)
                    or any(v is not None and not (k == "exclude" and v == []) for k, v in inner.args.items()
                           if k not in {"expressions", "from_", "where"})
                    or len(inner.selects) != 1 or inner.selects[0] != exp.Literal.number(1)):
                continue
            relation = inner.args.get("from_")
            relation = relation.this if relation else None
            if (not isinstance(relation, exp.Table) or not isinstance(relation.this, exp.Identifier)
                    or relation.alias_column_names
                    or any(v is not None for k, v in relation.args.items()
                           if k not in {"this", "db", "catalog", "alias"})):
                continue
            predicate = inner.args.get("where")
            if not predicate or predicate.find(exp.Select, exp.Window, exp.AggFunc):
                continue
            parts = list(predicate.this.flatten() if isinstance(predicate.this, exp.And) else [predicate.this])
            inner_name = relation.alias_or_name
            key, residual, valid = None, [], True
            for part in parts:
                columns = list(part.find_all(exp.Column))
                if any(not c.table for c in columns):
                    valid = False
                    break
                if all(c.table == inner_name for c in columns):
                    residual.append(part.copy())
                    continue
                if (key is not None or not isinstance(part, exp.EQ)
                        or not isinstance(part.this, exp.Column) or not isinstance(part.expression, exp.Column)):
                    valid = False
                    break
                a, b = part.this, part.expression
                if b.table == inner_name:
                    a, b = b, a
                if a.table != inner_name or b.table == inner_name or b.table not in scope.selected_sources:
                    valid = False
                    break
                key = a, b
            if valid and key is not None:
                a, b = key
                membership = exp.select(a.copy()).from_(relation.copy())
                if residual:
                    membership = membership.where(exp.and_(*residual))
                term.replace(exp.In(this=b.copy(), query=membership.subquery()))
    return tree


def prune_source_projections(authored, expanded, qualified):
    """Delete only proven-dead authored projections; never move or inline a macro.

    Dependencies come from the expanded, qualified query, including identifiers
    hidden in string arguments. Scope/projection positions must map one-to-one.
    """
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

    # This rule does not move predicates or cross windows/limits. Reuse the
    # conservative shape guard after masking just those supported boundaries.
    guard = bound.copy()
    for query in guard.find_all(exp.Select):
        for key in ("limit", "offset", "qualify"):
            query.set(key, None)
    for window in list(guard.find_all(exp.Window)):
        window.replace(exp.Literal.number(0))
    if not (plain_queries(guard, aggregates=True) and plain_joins(guard)):
        return result
    if any(node.alias_column_names for node in authored.find_all(exp.CTE, exp.Table, exp.Subquery)):
        return result

    originals = {}
    safe_aggregates = (exp.Count, exp.Sum, exp.Min, exp.Max, exp.Avg)
    for index, (query, source) in enumerate(zip(bound_queries, queries)):
        query.meta["extra_projection_scope"] = index
        for position, projection in enumerate(query.selects):
            projection.meta["extra_projection_position"] = position
        originals[index] = list(source.selects)

    # Rebuild scopes each pass so dependencies of deleted projections disappear.
    # Union requirements from ALL consumers before pruning shared CTE outputs.
    while True:
        scopes = list(traverse_scope(bound))
        required = {id(scope): set() for scope in scopes}
        for scope in scopes:
            for column in scope.columns:
                source = scope.sources.get(column.table)
                if isinstance(source, Scope):
                    required[id(source)].add(column.name)
        changed = False
        for scope in scopes:
            query = scope.expression
            if scope.is_root or query.args.get("distinct"):
                continue
            # Preserve aggregate cardinality, ordinal bindings, and local output
            # aliases used by ORDER BY/HAVING/QUALIFY, even if not selected above.
            if (not query.args.get("group") and query.find(exp.AggFunc)
                    or any(clause and clause.find(exp.Literal)
                           for clause in (query.args.get("order"), query.args.get("group")))):
                continue
            local = {c.name for key, clause in query.args.items()
                     if key not in {"expressions", "with_", "from_", "joins"}
                     and isinstance(clause, exp.Expression)
                     for c in clause.find_all(exp.Column) if not c.table}
            index = query.meta["extra_projection_scope"]
            source = queries[index]
            group, order = source.args.get("group"), source.args.get("order")
            if (group and any(v for k, v in group.args.items() if k != "expressions")
                    or any(clause and clause.find(exp.Literal) for clause in (group, order))
                    or order and any(v.name.upper() == "ALL" for v in order.find_all(exp.Var))):
                continue
            # Qualification may inline lateral projection / clause aliases. We
            # only delete from authored SQL, so retain those original bindings.
            expanded_source = expanded_queries[index]
            alias_references = {c.name.casefold() for key, clause in expanded_source.args.items()
                                if key != "with_"
                                for item in (clause if isinstance(clause, list) else [clause])
                                if isinstance(item, exp.Expression)
                                for c in item.find_all(exp.Column) if not c.table}
            local |= {p.output_name for p in query.selects
                      if originals[index][p.meta["extra_projection_position"]].output_name.casefold()
                      in alias_references}
            kept = []
            for projection in query.selects:
                position = projection.meta["extra_projection_position"]
                original = originals[index][position]
                value = projection.this if isinstance(projection, exp.Alias) else projection
                removable = (isinstance(value, (exp.Column, *safe_aggregates))
                             and not original.find(exp.Anonymous)
                             and not any(n.comments for n in original.walk()))
                if not removable or projection.output_name in required[id(scope)] | local:
                    kept.append(projection)
            # Never synthesize a constant or remove the last aggregate/output.
            if kept and len(kept) < len(query.selects):
                query.set("expressions", kept)
                changed = True
        if not changed:
            break
    for query in bound_queries:
        index = query.meta["extra_projection_scope"]
        queries[index].set("expressions", [originals[index][p.meta["extra_projection_position"]]
                                           for p in query.selects])
    return result


def short_names():
    index = 0
    while True:
        value, name = index, ""
        while True:
            value, digit = divmod(value, 26)
            name = chr(97 + digit) + name
            if not value:
                break
            value -= 1
        yield name
        index += 1


def generated_aliases(tree, occupied):
    """Rename only generated relation aliases, using native scope bindings."""
    names = short_names()
    occupied = set(occupied)
    for scope in traverse_scope(tree):
        for old, (node, _) in list(scope.selected_sources.items()):
            if not isinstance(node, (exp.Table, exp.Subquery)) or node.meta.get("extra_explicit_alias"):
                continue
            alias = node.args.get("alias")
            if not alias:
                continue
            name = next(names)
            while name in occupied:
                name = next(names)
            occupied.add(name)
            alias.set("this", exp.to_identifier(name))
            for column in scope.columns:
                if column.table == old:
                    column.set("table", exp.to_identifier(name))
    return tree


def redundant_aliases(tree):
    for alias in list(tree.find_all(exp.Alias)):
        column, name = alias.this, alias.args["alias"]
        if (isinstance(column, exp.Column) and not column.is_star
                and column.this == name and not alias.comments):
            alias.replace(column.copy())
    return tree
