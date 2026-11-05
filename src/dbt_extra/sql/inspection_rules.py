"""Guarded structural rewrites for read-only inspection, not authored SQL edits."""

from sqlglot import exp
from sqlglot.optimizer.eliminate_subqueries import eliminate_subqueries
from sqlglot.optimizer.normalize import normalize
from sqlglot.optimizer.optimize_joins import optimize_joins
from sqlglot.optimizer.pushdown_predicates import pushdown_predicates
from sqlglot.optimizer.scope import traverse_scope

from dbt_extra.sql.scopes import volatile
from dbt_extra.sql.functions import function_spec, has_generators


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
    if (not plain_queries(tree, aggregates=True) or tree.find(exp.With) or volatile(tree)
            or any(table.meta.get("extra_owner") for table in tree.find_all(exp.Table))
            or any(not isinstance(agg, (exp.Count, exp.Sum, exp.Min, exp.Max, exp.Avg))
                   for agg in tree.find_all(exp.AggFunc))):
        return tree
    queries = [node.this for node in tree.find_all(exp.Subquery)]
    if len(set(queries)) < len(queries):
        return eliminate_subqueries(tree)
    return tree
