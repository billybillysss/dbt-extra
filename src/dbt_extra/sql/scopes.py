"""Physical relation traversal and stable authored query-scope addresses."""

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope


def relation_tables(tree):
    """Yield physical relation nodes, excluding references to scoped SQL CTEs."""
    for scope in traverse_scope(tree):
        for table in scope.tables:
            if len(table.parts) == 1 and isinstance(scope.sources.get(table.alias_or_name), Scope):
                continue
            yield table


def query_scopes(tree):
    """Address named CTEs by AST path, not potentially shadowed names."""
    result = []

    def visit(node, path):
        if isinstance(node, exp.CTE):
            result.append((node.alias, path + ["this"], node.this))
        for key, value in node.args.items():
            if isinstance(value, exp.Expression):
                visit(value, path + [key])
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    if isinstance(child, exp.Expression):
                        visit(child, path + [key, index])

    visit(tree, [])
    return result + [("OUTPUT", [], tree)]


def scope_at(tree, path):
    node = tree
    for key in path:
        node = node[key] if isinstance(key, int) else node.args[key]
    return node
