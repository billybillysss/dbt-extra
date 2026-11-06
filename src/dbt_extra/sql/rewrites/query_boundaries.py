"""Remove identity boundaries without moving evaluation across SQL clauses.

These rules deliberately do not use the general-purpose movement proof: copying
a child's unchanged projection through a column-only wrapper does not duplicate
or relocate its expressions, even when the child contains aggregates or casts.
"""

from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from dbt_extra.sql.safety import has_evaluation_barrier
from dbt_extra.sql.functions import has_generators


def _only(query, allowed):
    return all(not value or key in allowed for key, value in query.args.items())


def inline_single_input_ctes(tree):
    """Inline a single CTE consumer, without duplicating or reordering its work."""
    for scope in list(traverse_scope(tree)):
        query = scope.expression
        if not isinstance(query, exp.Select) or not _only(query, {"expressions", "from_", "with_"}):
            continue
        source = query.args.get("from_")
        table = source.this if source else None
        with_ = query.args.get("with_")
        if not isinstance(table, exp.Table) or not with_ or with_.args.get("recursive"):
            continue
        if len(with_.expressions) != 1 or with_.comments or not _only(with_, {"expressions"}):
            continue
        cte = with_.expressions[0]
        if (cte.alias != table.name or cte.alias_column_names or cte.comments
                or not _only(cte, {"this", "alias"}) or cte.args.get("materialized") is not None
                or not _only(table, {"this", "alias"}) or table.comments
                or has_evaluation_barrier(cte.this) or has_generators(cte.this)):
            continue
        # Self-reference, nested consumers and correlation are not single-use
        # identity boundaries, even if the top-level FROM has only one input.
        if any(s.external_columns for s in traverse_scope(cte.this)):
            continue
        consumers = [t for t in query.find_all(exp.Table) if t.name == cte.alias and not t.db and not t.catalog]
        if consumers != [table]:
            continue
        alias = table.args.get("alias") or exp.TableAlias(this=cte.args["alias"].this.copy())
        table.replace(exp.Subquery(this=cte.this.copy(), alias=alias.copy()))
        query.set("with_", None)
    return tree


def unwrap_column_projections(tree, dialect):
    """Compose column-only SELECTs; never move predicates or duplicate work."""
    for outer in reversed(list(tree.find_all(exp.Select))):
        if outer.comments or not _only(outer, {"expressions", "from_"}):
            continue
        from_ = outer.args.get("from_")
        subquery = from_.this if from_ else None
        if (not isinstance(subquery, exp.Subquery) or subquery.comments or subquery.alias_column_names
                or not _only(subquery, {"this", "alias"}) or not isinstance(subquery.this, exp.Select)):
            continue
        inner = subquery.this
        # Positional/lateral output bindings, set shapes and row/order-sensitive
        # clauses need their own proof. Keep them rather than rebinding names.
        if not _only(inner, {"expressions", "from_", "joins", "where", "group", "with_"}):
            continue
        group = inner.args.get("group")
        if group and any(isinstance(n, (exp.Literal, exp.Var)) for n in group.walk()):
            continue
        outputs = {p.output_name: p for p in inner.selects}
        if len(outputs) != len(inner.selects) or any(p.is_star for p in inner.selects):
            continue
        columns = [p.unalias() for p in outer.selects]
        if any(not isinstance(c, exp.Column) or c.is_star or c.table != subquery.alias
               or c.name not in outputs for c in columns):
            continue
        names = [c.name for c in columns]
        if len(names) != len(set(names)):
            continue
        # Pruning is handled separately, including global-aggregate cardinality
        # and observable unused expressions. This pass must erase no evaluation.
        if names != list(outputs):
            continue
        # Preserve any lateral aliases in SELECT and alias-based GROUP BY.
        if any(not c.table for p in inner.selects for c in p.find_all(exp.Column)):
            continue
        if group and any(not c.table for c in group.find_all(exp.Column)):
            continue
        replacement = inner.copy()
        projections = []
        for projection, column in zip(outer.selects, columns):
            value = outputs[column.name].copy()
            if value.output_name != projection.output_name or isinstance(projection, exp.Alias):
                alias = projection.args.get("alias") or column.this
                value = exp.Alias(this=value.unalias().copy(), alias=alias.copy())
            projections.append(value)
        replacement.set("expressions", projections)
        if outer is tree:
            tree = replacement
        else:
            outer.replace(replacement)
    return tree


def simplify_query_boundaries(tree, dialect):
    # Each iteration removes at least one boundary; stop on structural stability.
    while True:
        before = tree.copy()
        tree = unwrap_column_projections(inline_single_input_ctes(tree), dialect)
        if tree == before:
            return tree
