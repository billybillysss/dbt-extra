"""Guarded predicate, join and subquery transformations."""

from sqlglot import exp
from sqlglot.optimizer.eliminate_subqueries import eliminate_subqueries
from sqlglot.optimizer.normalize import normalize
from sqlglot.optimizer.optimize_joins import optimize_joins
from sqlglot.optimizer.pushdown_predicates import pushdown_predicates
from sqlglot.optimizer.scope import Scope, traverse_scope

from dbt_extra.sql.safety import has_evaluation_barrier
from dbt_extra.sql.dialects import INTEGER_MEMBERSHIP_DIALECTS
from dbt_extra.sql.rewrites.expressions import predicate_simplification_safe
from dbt_extra.sql.functions import function_spec, has_generators


def collapse_complementary_union(tree):
    """Combine identical UNION ALL scans with complementary equality filters.

    Keep both comparisons and their coercions: NULLs match neither = nor <>.
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


def decorrelate_filter_exists(tree, *, dialect=None, schema=None):
    """Positive WHERE EXISTS with one proven integral equality becomes IN.

    Only conjunctive WHERE terms, SELECT 1 over one plain table, and qualified
    inner-only residuals are accepted. FALSE and UNKNOWN both reject a row here;
    this is not valid in a SELECT or NOT. Matching declared integral base-column
    types on execution-tested dialects are required to preserve coercions.
    """
    if dialect not in INTEGER_MEMBERSHIP_DIALECTS or schema is None:
        return tree
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
            if (not predicate or predicate.find(exp.Select, exp.Window, exp.AggFunc)
                    or not predicate_simplification_safe(inner)):
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
                source = scope.sources.get(b.table)
                inner_scope = next((s for s in scope.subquery_scopes if s.expression is inner), None)
                inner_source = inner_scope.sources.get(inner_name) if inner_scope else None
                if (not isinstance(source, exp.Table) or source.alias_column_names
                        or not isinstance(inner_source, exp.Table)):
                    continue
                inner_type = schema.get_column_type(relation, a)
                outer_type = schema.get_column_type(source, b)
                if (inner_type != outer_type or inner_type not in tuple(
                        exp.DataType.build(t) for t in ("TINYINT", "SMALLINT", "INT", "BIGINT"))):
                    continue
                membership = exp.select(a.copy()).from_(relation.copy())
                if residual:
                    membership = membership.where(exp.and_(*residual))
                term.replace(exp.In(this=b.copy(), query=membership.subquery()))
    return tree


def normalize_predicates(tree):
    # Normal-form expansion can grow exponentially; keep inspection bounded.
    return normalize(tree, max_distance=32)


def plain_queries(tree, *, aggregates=False):
    """Reject semantic barriers rather than moving expressions across them."""
    if has_generators(tree):
        return False
    allowed = {"expressions", "from_", "joins", "where", "distinct", "order", "with_"}
    if aggregates:
        allowed |= {"group", "having"}
    for node in tree.walk():
        spec = function_spec(node)
        if spec and spec.kind in {"aggregate", "window"}:
            # Local aggregates are deliberately not handed to SQLGlot rules
            # expecting a native AggFunc, even when aggregates=True.
            return False
        if isinstance(node, exp.Select):
            if any(v is not None and k not in allowed and not (k == "exclude" and v == [])
                   for k, v in node.args.items()):
                return False
            distinct = node.args.get("distinct")
            if distinct and distinct.args.get("on"):
                return False
        elif isinstance(node, exp.Subquery):
            if (not isinstance(node.parent, (exp.From, exp.Join))
                    or not isinstance(node.this, exp.Select)
                    or any(v is not None and k not in {"this", "alias"} for k, v in node.args.items())):
                return False
        elif isinstance(node, exp.Table):
            if (not isinstance(node.this, exp.Identifier)
                    or any(v is not None and k not in {"this", "db", "catalog", "alias"}
                           for k, v in node.args.items())):
                return False
        elif isinstance(node, (exp.From, exp.Join)):
            if not isinstance(node.this, (exp.Table, exp.Subquery)):
                return False
        elif isinstance(node, exp.CTE):
            if any(v is not None and k not in {"this", "alias"} for k, v in node.args.items()):
                return False
        elif isinstance(node, exp.With) and node.args.get("recursive"):
            return False
        elif isinstance(node, (exp.Window, exp.SetOperation, exp.Lateral)):
            return False
        elif isinstance(node, exp.AggFunc) and not aggregates:
            return False
    return not any(scope.external_columns for scope in traverse_scope(tree))


def plain_joins(tree):
    return all(not join.side and join.kind in {"", "INNER", "CROSS"}
               and not (join.kind == "CROSS" and join.args.get("on") is not None)
               and not any(v is not None and k not in {"this", "on", "kind"}
                           for k, v in join.args.items())
               for join in tree.find_all(exp.Join))


def pushdown_safe_predicates(tree, dialect=None):
    # SQLGlot 30.8 can push a filter below LIMIT/OFFSET or a global aggregate,
    # changing which rows (or how many rows) survive. Use a query-wide guard.
    if plain_queries(tree) and plain_joins(tree):
        return pushdown_predicates(tree, dialect=dialect)
    return tree


def optimize_safe_joins(tree):
    # Splitting an OR across joins is not equivalent to splitting an AND.
    if (plain_queries(tree) and plain_joins(tree)
            and not any(join.args.get("on") is not None and join.args["on"].find(exp.Or)
                        for join in tree.find_all(exp.Join))):
        return optimize_joins(tree)
    return tree


def deduplicate_subqueries(tree):
    # This rule factors derived tables into CTEs; it does not flatten them.
    # Avoid lifting scoped CTE names, correlated/limited queries, stored-self
    # metadata, or order-sensitive aggregates into a shared definition.
    if (not plain_queries(tree, aggregates=True) or tree.find(exp.With) or has_evaluation_barrier(tree)
            or any(table.meta.get("extra_owner") for table in tree.find_all(exp.Table))
            or any(not isinstance(agg, (exp.Count, exp.Sum, exp.Min, exp.Max, exp.Avg))
                   for agg in tree.find_all(exp.AggFunc))):
        return tree
    queries = [node.this for node in tree.find_all(exp.Subquery)]
    if len(set(queries)) < len(queries):
        return eliminate_subqueries(tree)
    return tree
