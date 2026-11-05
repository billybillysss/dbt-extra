"""Dialect-local semantics for demonstrated SQLGlot Anonymous-function gaps.

Keep the original AST/spelling. Recognition, value type, output shape and rewrite
permission are separate facts; no global parser or SQLGlot registry is modified.
"""

from dataclasses import dataclass

from sqlglot import exp


@dataclass(frozen=True)
class Function:
    name: str
    example: str
    returns: str | None
    minimum: int
    maximum: int | None
    kind: str = "scalar"
    volatility: str = "immutable"
    may_raise: bool = True


@dataclass(frozen=True)
class Shape:
    kind: str
    columns: int | None
    rows: str


# Import data only after defining the shared record (no dialect inheritance).
from dbt_extra.sql.functions.spark import FUNCTIONS as SPARK  # noqa: E402
from dbt_extra.sql.functions.tsql import FUNCTIONS as TSQL  # noqa: E402

CATALOG = {"spark": {f.name: f for f in SPARK}, "tsql": {f.name: f for f in TSQL}}


def function_spec(node, dialect=None):
    """Recognize only unqualified, unquoted built-ins with supported arity."""
    if not isinstance(node, exp.Anonymous) or isinstance(node.parent, exp.Dot):
        return None
    if isinstance(node.this, exp.Identifier) and node.this.quoted:
        return None
    dialect = dialect or node.meta.get("extra_function_dialect")
    spec = CATALOG.get(dialect, {}).get(node.name.lower())
    count = len(node.expressions)
    if spec and count >= spec.minimum and (spec.maximum is None or count <= spec.maximum):
        return spec
    return None


def recognize_functions(tree, dialect):
    """Mark the dialect, not a cached permission that could outlive an AST edit."""
    for node in tree.find_all(exp.Anonymous):
        node.meta["extra_function_dialect"] = dialect
    return tree


def function_shape(node, dialect=None):
    spec = function_spec(node, dialect)
    if spec is None:
        return Shape("unknown", None, "unknown")
    if spec.kind != "generator":
        return Shape(spec.kind, 1, "one_per_group" if spec.kind == "aggregate" else "one_per_row")
    if spec.name == "json_tuple":
        return Shape("generator", len(node.expressions) - 1, "one_per_row")
    if spec.name == "string_split":
        columns = 1
        if len(node.expressions) == 3:
            flag = node.expressions[2]
            columns = 1 + int(flag.this) if isinstance(flag, exp.Literal) and not flag.is_string and flag.this in {"0", "1"} else None
        return Shape("generator", columns, "zero_or_more")
    if spec.name in {"window", "session_window"}:
        # Spark grouping expressions have expansion/session semantics, not
        # freely movable scalar calls, despite returning a single struct column.
        return Shape("generator", 1, "zero_or_more" if spec.name == "window" else "unknown")
    array = node.expressions[0]
    if isinstance(array, exp.Array) and array.expressions:
        structs = array.expressions
        widths = {len(s.expressions) for s in structs if isinstance(s, exp.Struct)}
        if all(isinstance(s, exp.Struct) for s in structs) and len(widths) == 1:
            return Shape("generator", widths.pop(), "one_or_more")
    return Shape("generator", None, "one_or_more")  # INLINE_OUTER: input struct controls arity.


def function_barrier(node):
    """Unknown, non-scalar, context-sensitive or fallible calls cannot be moved.

    Currently all local gaps remain rewrite barriers. A return type is not proof
    that evaluation can be removed, duplicated, folded or reordered.
    """
    spec = function_spec(node)
    return spec is None or spec.kind != "scalar" or spec.volatility != "immutable" or spec.may_raise


def has_generators(tree):
    return any((isinstance(n, exp.Anonymous) and function_shape(n).kind == "generator")
               or isinstance(n, exp.UDTF) for n in tree.walk())
