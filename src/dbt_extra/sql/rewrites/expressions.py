"""Local authored-expression rules with explicit type and macro boundaries."""

from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from dbt_extra.sql.dialects import INTEGER_ADD_ZERO_DIALECTS, INTEGER_LITERAL_FOLD_DIALECTS


def _integer(node):
    if isinstance(node, exp.Literal) and node.is_int:
        value = int(node.this)
        if 0 <= value <= 2147483647:
            return value
    return None


def _input_types(tree, schema):
    """Use declared base-input types, not inferred arithmetic/aggregate types."""
    types = {}
    if schema is not None:
        for scope in traverse_scope(tree):
            for column in scope.columns:
                source = scope.sources.get(column.table)
                if isinstance(source, exp.Table):
                    types[id(column)] = schema.get_column_type(source, column)
    return types


def simplify_source_expressions(tree, dialect, *, schema=None, macros=()):
    """Simplify in place, without moving expressions or changing scope interfaces.

    A query-wide window/aggregate/limit is not a barrier to local constant work.
    Decimal precision, integer overflow, positional bindings, comments, and opaque
    macro subtrees are barriers. Unknown input types are never guessed.
    """
    types = _input_types(tree, schema)
    macros = set(macros)
    for node in reversed(list(tree.walk())):
        if not isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.And, exp.Or, exp.EQ, exp.NEQ)):
            continue
        if (node.find_ancestor(exp.Order, exp.Group)
                or any(isinstance(parent.parent, exp.Select)
                       and parent in parent.parent.selects
                       and not isinstance(parent, (exp.Alias, exp.Column))
                       for parent in _ancestors(node))
                or any(n.comments or isinstance(n, exp.Anonymous) and n.name in macros
                       for n in node.walk())):
            continue
        replacement = None
        if isinstance(node, (exp.Add, exp.Sub, exp.Mul)):
            a, b = _integer(node.this), _integer(node.expression)
            if a is not None and b is not None and dialect in INTEGER_LITERAL_FOLD_DIALECTS:
                value = a + b if isinstance(node, exp.Add) else a - b if isinstance(node, exp.Sub) else a * b
                # Keep both the literal type class and runtime overflow behavior.
                if 0 <= value <= 2147483647:
                    replacement = exp.Literal.number(value)
            # DuckDB INT/BIGINT + integer zero keeps the exact input type. Do not
            # generalize to DECIMAL, unknown types, computed inputs or dialects.
            elif (dialect in INTEGER_ADD_ZERO_DIALECTS and isinstance(node, exp.Add) and b == 0
                  and isinstance(node.this, exp.Column)
                  and types.get(id(node.this)) in (exp.DataType.build("INT"), exp.DataType.build("BIGINT"))):
                replacement = node.this.copy()
        elif isinstance(node, (exp.And, exp.Or)):
            identity = isinstance(node, exp.And)
            for literal, other in ((node.this, node.expression), (node.expression, node.this)):
                # A bare numeric/string/unknown-macro operand may be coerced to
                # BOOLEAN by AND/OR; returning it would change an output's type.
                if (isinstance(literal, exp.Boolean) and literal.this is identity
                        and isinstance(other.unnest(), (exp.Predicate, exp.Boolean, exp.Connector, exp.Not))):
                    replacement = other.copy()
                    break
        elif isinstance(node, (exp.EQ, exp.NEQ)):
            a, b = _integer(node.this), _integer(node.expression)
            if a is not None and b is not None:
                replacement = exp.convert((a == b) if isinstance(node, exp.EQ) else (a != b))
        if replacement is not None:
            node.replace(replacement)
    for where in list(tree.find_all(exp.Where)):
        if where.this.unnest() == exp.true() and not any(n.comments for n in where.walk()):
            where.parent.set("where", None)
    return tree


def _ancestors(node):
    # Database labels for unnamed computed outputs can depend on their complete
    # rendered expression, not SQLGlot's (often empty) output_name.
    while node is not None:
        yield node
        node = node.parent


def predicate_simplification_safe(tree):
    """Guard third-party rules that invoke unrestricted simplify on predicates.

    Projection arithmetic is untouched by predicate pushdown. Arithmetic, casts,
    functions and mixed-type constant comparisons inside predicates are not
    entrusted to that simplifier (which can erase overflow/coercion errors).
    """
    allowed = (exp.Column, exp.Identifier, exp.Literal, exp.Boolean, exp.Null,
               exp.Paren, exp.And, exp.Or, exp.Not, exp.EQ, exp.NEQ, exp.GT,
               exp.GTE, exp.LT, exp.LTE, exp.Is)
    for clause in tree.find_all(exp.Where, exp.Having, exp.Qualify, exp.Join, exp.Connector):
        if isinstance(clause, exp.Join):
            predicate = clause.args.get("on")
        elif isinstance(clause, exp.Connector):
            predicate = clause
        else:
            predicate = clause.this
        if predicate is None:
            continue
        if any(not isinstance(n, allowed) for n in predicate.walk()):
            return False
        for comparison in predicate.find_all(exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE):
            a, b = comparison.this, comparison.expression
            if isinstance(a, exp.Literal) and isinstance(b, exp.Literal) and a.is_string != b.is_string:
                return False
    return True


def retained_boundaries(tree):
    """Explain common intentional non-rewrites, without claiming warehouse costs."""
    notes = []
    if any(isinstance(n, (exp.Add, exp.Sub)) and _integer(n.expression) == 0
           or isinstance(n, exp.Mul) and _integer(n.expression) == 1 for n in tree.walk()):
        notes.append("Arithmetic identity retained: exact result types/coercions are not proven safe to remove.")
    if any(s.args.get("distinct") for s in tree.find_all(exp.Select)):
        notes.append("DISTINCT tuple retained to preserve row multiplicity.")
    if tree.find(exp.Window, exp.Limit, exp.Offset, exp.AggFunc):
        notes.append("Aggregate, window and row-limit boundaries restrict expression movement, not safe local simplification.")
    return notes
