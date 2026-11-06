"""Effect proofs are deliberately smaller than the set of recognized functions."""

from dataclasses import dataclass

from sqlglot import exp

from dbt_extra.sql.functions.registry import dialect_key, function_barrier, function_shape, function_spec


# Positive, bounded effect evidence. New SQLGlot nodes must not silently acquire
# sharing/inlining permission merely because the dependency learned their syntax.
# These operations can still raise; immutability is not a removal/movement proof.
IMMUTABLE_NATIVE_FUNCTIONS = frozenset("""
abs acos asin atan atan2 ceil floor round pow sqrt ln log exp sign
upper lower length substring concat concatws trim ltrim rtrim replace reverse
split splitpart left right md5 sha sha2 coalesce nullif if case cast trycast and or not
sum avg min max count rownumber rank denserank ntile percentrank cumedist
lag lead firstvalue lastvalue nthvalue stddev stddevpop stddevsamp variance variancepop
array arrayagg arrayposition arraysize arraycontains arrayconcat arraydistinct
arraysort arraycompact arrayfilter transform map struct
dateadd datediff datetrunc timestamptrunc extract strtodate strtotime datetostr timetostr
parsejson tojson jsonextract jsonextractscalar jsonformat typeof isarray tonumber
""".split())


@dataclass(frozen=True)
class FunctionProperties:
    known: bool
    kind: str
    volatility: str
    may_raise: bool
    columns: int | None
    output_type: str | None


def function_properties(node, dialect=None):
    if isinstance(node, exp.Anonymous):
        spec = function_spec(node, dialect)
        shape = function_shape(node, dialect)
        volatility = "statement_stable" if spec and spec.volatility == "stable" else spec.volatility if spec else "unknown"
        return FunctionProperties(bool(spec), shape.kind, volatility,
                                  spec.may_raise if spec else True, shape.columns, spec.returns if spec else None)
    kind = "aggregate" if isinstance(node, exp.AggFunc) else "window" if isinstance(node, (exp.Window, exp.RowNumber, exp.Rank, exp.DenseRank)) else "generator" if isinstance(node, exp.UDTF) else "scalar"
    if node.key in {"rand", "randn", "randstr", "uuid", "nextvaluefor", "seq1", "seq2", "seq4", "seq8", "shuffle", "uniform"}:
        return FunctionProperties(True, kind, "volatile", True, 1, None)
    if node.key.startswith("ai") or node.key in {"secret", "externalquery"}:
        # External services, secrets and model invocations are opaque effects,
        # even when SQLGlot gives them a native scalar AST and a return type.
        return FunctionProperties(True, kind, "unknown", True, 1, None)
    if node.key.startswith("current") or node.key in {"sessionuser", "sessionparameter"}:
        # Native context functions are not immutable merely because SQLGlot
        # recognizes them. Keep session/statement observations behind a barrier.
        clock = node.key in {"currenttimestamp", "currentdate", "currenttime"}
        return FunctionProperties(True, kind, "statement_stable", not clock, 1, None)
    # Native recognition alone is not a proof of totality (SUM, casts, arithmetic,
    # string functions and dialect coercions can all raise).
    total = isinstance(node, (exp.Count, exp.RowNumber)) and dialect_key(node, dialect) in {"duckdb", "spark"}
    output = "INT" if isinstance(node, exp.RowNumber) and dialect_key(node, dialect) == "spark" else "BIGINT"
    effect = "immutable" if node.key in IMMUTABLE_NATIVE_FUNCTIONS else "unknown"
    return FunctionProperties(True, kind, effect, not total, 1, output if total else None)


def has_evaluation_barrier(tree):
    """Block sharing of unknown/effectful calls, not just volatile functions.

    Anonymous calls also require the registry's scalar/totality proof. Native
    immutable calls retain their existing sharing policy; removal and movement
    require the separate, stricter proofs below.
    """
    return any((isinstance(n, exp.Anonymous) and function_barrier(n))
               or (isinstance(n, exp.Func) and function_properties(n).volatility != "immutable")
               for n in tree.walk())


def discardable(expression, dialect=None):
    """No fallible/volatile/unknown evaluation is erased. No schema types guessed."""
    allowed = (exp.Alias, exp.Column, exp.Identifier, exp.Literal, exp.Null, exp.Boolean,
               exp.Paren, exp.Star, exp.Count, exp.RowNumber, exp.Window, exp.Order,
               exp.Ordered, exp.WindowSpec)
    for node in expression.walk():
        if node.comments:
            return False
        if isinstance(node, exp.Anonymous):
            # Only the null-check operation is total for every input type. Its
            # arguments must independently pass this same walk. This permission
            # erases unused outputs only; catalog movement barriers stay intact.
            spec = function_spec(node, dialect)
            if (dialect_key(node, dialect) not in {"spark", "databricks"}
                    or spec is None or spec.name not in {"isnull", "isnotnull"}):
                return False
        elif not isinstance(node, allowed):
            return False
        elif isinstance(node, exp.Func):
            properties = function_properties(node, dialect)
            if properties.may_raise or properties.volatility != "immutable":
                return False
    return True


def movable(tree):
    """Conservative total expressions for rules which may change evaluation count."""
    allowed = (exp.Query, exp.Subquery, exp.From, exp.Table, exp.TableAlias, exp.Join,
               exp.With, exp.CTE, exp.Where, exp.Distinct, exp.Order, exp.Ordered,
               exp.Alias, exp.Column, exp.Identifier, exp.Literal, exp.Null, exp.Boolean,
               exp.Paren, exp.And, exp.Or, exp.Not, exp.EQ, exp.NEQ, exp.GT, exp.GTE,
               exp.LT, exp.LTE, exp.Is, exp.Star)
    return all(isinstance(n, allowed) and not n.comments for n in tree.walk())
