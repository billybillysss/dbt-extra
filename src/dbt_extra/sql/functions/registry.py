"""Dialect-local semantics for demonstrated SQLGlot Anonymous-function gaps.

Keep the original AST/spelling. Recognition, value type, output shape and rewrite
permission are separate facts; no global parser or SQLGlot registry is modified.
"""

from sqlglot import exp

from dbt_extra.sql.functions.models import FunctionShape

# Dialect catalogs depend only on the shared records (no dialect inheritance).
from dbt_extra.sql.functions.athena import FUNCTIONS as ATHENA
from dbt_extra.sql.functions.bigquery import FUNCTIONS as BIGQUERY
from dbt_extra.sql.functions.databricks import FUNCTIONS as DATABRICKS
from dbt_extra.sql.functions.duckdb import FUNCTIONS as DUCKDB
from dbt_extra.sql.functions.fabric import FUNCTIONS as FABRIC
from dbt_extra.sql.functions.postgres import FUNCTIONS as POSTGRES
from dbt_extra.sql.functions.redshift import FUNCTIONS as REDSHIFT
from dbt_extra.sql.functions.snowflake import FUNCTIONS as SNOWFLAKE
from dbt_extra.sql.functions.spark import FUNCTIONS as SPARK
from dbt_extra.sql.functions.trino import FUNCTIONS as TRINO
from dbt_extra.sql.functions.tsql import FUNCTIONS as TSQL


def _catalog(functions):
    """Validate the source sequence before a dict could silently erase duplicates."""
    catalog = {}
    for spec in functions:
        name = spec.name.lower()
        if name in catalog:
            raise ValueError(f"Duplicate function name: {name}")
        if spec.name != name:
            raise ValueError(f"Function names must be lowercase: {spec.name}")
        if spec.minimum < 0 or (spec.maximum is not None and spec.maximum < spec.minimum):
            raise ValueError(f"Invalid function arity: {name}")
        if spec.arities is not None and (
            not spec.arities or tuple(sorted(set(spec.arities))) != spec.arities
            or any(n < spec.minimum or (spec.maximum is not None and n > spec.maximum)
                   for n in spec.arities)
        ):
            raise ValueError(f"Invalid function arities: {name}")
        if spec.kind not in {"scalar", "aggregate", "window", "generator"}:
            raise ValueError(f"Invalid function kind: {name}: {spec.kind}")
        if spec.volatility not in {"immutable", "stable", "volatile", "unknown"}:
            raise ValueError(f"Invalid function volatility: {name}: {spec.volatility}")
        catalog[name] = spec
    return catalog


CATALOG = {
    "athena": _catalog(ATHENA),
    "bigquery": _catalog(BIGQUERY),
    "databricks": _catalog(DATABRICKS),
    "duckdb": _catalog(DUCKDB),
    "fabric": _catalog(FABRIC),
    "postgres": _catalog(POSTGRES),
    "redshift": _catalog(REDSHIFT),
    "snowflake": _catalog(SNOWFLAKE),
    "spark": _catalog(SPARK),
    "trino": _catalog(TRINO),
    "tsql": _catalog(TSQL),
}


def dialect_key(node, dialect):
    # Callers validate dialects through the shared resolver/parser. Strip settings
    # only for catalog selection, never from AST metadata or parsing/type inference.
    # Exact names are deliberate: Databricks/Fabric do not inherit Spark/T-SQL.
    dialect = dialect or node.meta.get("extra_function_dialect")
    return dialect.partition(",")[0].strip().lower() if isinstance(dialect, str) else None


def function_spec(node, dialect=None):
    """Recognize only unqualified, unquoted built-ins with supported arity."""
    if not isinstance(node, exp.Anonymous) or isinstance(node.parent, exp.Dot):
        return None
    if isinstance(node.this, exp.Identifier) and node.this.quoted:
        return None
    spec = CATALOG.get(dialect_key(node, dialect), {}).get(node.name.lower())
    count = len(node.expressions)
    if (spec and count >= spec.minimum and (spec.maximum is None or count <= spec.maximum)
            and (spec.arities is None or count in spec.arities)):
        return spec
    return None


def recognize_functions(tree, dialect):
    """Mark the dialect, not a cached permission that could outlive an AST edit."""
    for node in tree.find_all(exp.Anonymous):
        node.meta["extra_function_dialect"] = dialect
    # This native node is a set-returning expression in PostgreSQL, but a
    # list-valued scalar in DuckDB. Do not classify it by spelling alone.
    for node in tree.find_all(exp.ExplodingGenerateSeries):
        node.meta["extra_function_dialect"] = dialect
    return tree


def function_shape(node, dialect=None):
    spec = function_spec(node, dialect)
    if spec is None:
        return FunctionShape("unknown", None, "unknown")
    if spec.kind != "generator":
        return FunctionShape(spec.kind, 1, "one_per_group" if spec.kind == "aggregate" else "one_per_row")
    key = (dialect_key(node, dialect), spec.name)
    if key in {("spark", "json_tuple"), ("databricks", "json_tuple")}:
        return FunctionShape("generator", len(node.expressions) - 1, "one_per_row")
    if key == ("fabric", "string_split"):
        return FunctionShape("generator", 1, "zero_or_more")
    if key in {("postgres", "jsonb_path_query"), ("postgres", "jsonb_each")}:
        return FunctionShape("generator", 2 if spec.name == "jsonb_each" else 1, "zero_or_more")
    if key in {("databricks", "variant_explode"), ("databricks", "variant_explode_outer")}:
        return FunctionShape("generator", 3, "one_or_more" if spec.name.endswith("_outer") else "zero_or_more")
    if key == ("tsql", "string_split"):
        columns = 1
        if len(node.expressions) == 3:
            flag = node.expressions[2]
            columns = 1 + int(flag.this) if isinstance(flag, exp.Literal) and not flag.is_string and flag.this in {"0", "1"} else None
        return FunctionShape("generator", columns, "zero_or_more")
    if key in {(d, name) for d in ("spark", "databricks") for name in ("window", "session_window")}:
        # Spark grouping expressions have expansion/session semantics, not
        # freely movable scalar calls, despite returning a single struct column.
        return FunctionShape("generator", 1, "zero_or_more" if spec.name == "window" else "unknown")
    if key in {("spark", "inline_outer"), ("databricks", "inline_outer")}:
        array = node.expressions[0]
        if isinstance(array, exp.Array) and array.expressions:
            structs = array.expressions
            widths = {len(s.expressions) for s in structs if isinstance(s, exp.Struct)}
            if all(isinstance(s, exp.Struct) for s in structs) and len(widths) == 1:
                return FunctionShape("generator", widths.pop(), "one_or_more")
        return FunctionShape("generator", None, "one_or_more")
    return FunctionShape("generator", None, "unknown")


def function_barrier(node):
    """Unknown, non-scalar, context-sensitive or fallible calls cannot be moved.

    Currently all local gaps remain rewrite barriers. A return type is not proof
    that evaluation can be removed, duplicated, folded or reordered.
    """
    spec = function_spec(node)
    return spec is None or spec.kind != "scalar" or spec.volatility != "immutable" or spec.may_raise


def has_generators(tree, dialect=None):
    return any((isinstance(n, exp.Anonymous) and function_shape(n, dialect).kind == "generator")
               or (isinstance(n, exp.ExplodingGenerateSeries) and dialect_key(n, dialect) == "postgres")
               or isinstance(n, exp.UDTF) for n in tree.walk())
