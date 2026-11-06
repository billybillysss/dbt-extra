"""Best-effort type inference from qualified SQL and declared schema evidence."""

from sqlglot import Dialect, exp
from sqlglot.optimizer.annotate_types import annotate_types

from dbt_extra.sql.renderer import sql
from dbt_extra.sql.functions import function_spec, has_generators, recognize_functions


# Demonstrated native inference gaps, not Anonymous registrations. These fixed
# return families are dialect-local and grant no evaluation/rewrite permission.
NATIVE_RETURN_TYPES = {
    "snowflake": {exp.IsArray: "BOOLEAN"},
    "redshift": {exp.Soundex: "VARCHAR", exp.JSONExtractScalar: "VARCHAR", exp.ParseJSON: "SUPER"},
    "trino": {exp.CurrentTimezone: "VARCHAR", exp.ArrayPosition: "BIGINT"},
    "athena": {exp.ArrayPosition: "BIGINT"},
    "postgres": {exp.ArrayPosition: "INTEGER"},
    "duckdb": {exp.ArrayPosition: "INTEGER", exp.StrPosition: "BIGINT", exp.Sign: "TINYINT",
               exp.UnixToTime: "TIMESTAMPTZ", exp.CurrentTime: "TIMETZ", exp.WeekOfYear: "BIGINT"},
    "spark": {exp.ArrayPosition: "BIGINT"},
    "databricks": {exp.ArrayPosition: "BIGINT", exp.ParseJSON: "VARIANT"},
}


def _argument_type(node):
    argument = node.this
    if isinstance(argument, exp.Distinct):
        argument = argument.expressions[0] if len(argument.expressions) == 1 else None
    return argument.type if isinstance(argument, exp.Expr) else None


def _decimal_parts(dtype):
    if dtype and dtype.is_type("DECIMAL") and len(dtype.expressions) == 2:
        values = [p.this for p in dtype.expressions]
        if all(isinstance(v, exp.Literal) and not v.is_string and v.this.isdigit() for v in values):
            return tuple(int(v.this) for v in values)
    return None


def _aggregate_type(node, dialect):
    """Reviewed numeric overloads only; unknown inputs never inherit a guessed type."""
    dtype = _argument_type(node)
    if dtype is None:
        return "UNKNOWN"
    integer = dtype.is_type("TINYINT", "SMALLINT", "INT", "BIGINT")
    floating = dtype.is_type("FLOAT", "DOUBLE")
    decimal = dtype.is_type("DECIMAL")
    parts = _decimal_parts(dtype)
    average = isinstance(node, exp.Avg)
    if dialect == "postgres":
        if decimal or (integer and (average or dtype.is_type("BIGINT"))):
            return "NUMERIC"
        if integer:
            return "BIGINT"
        if floating:
            return "DOUBLE" if average else dtype.copy()
        return dtype.copy() if dtype.is_type("INTERVAL", "MONEY") and not (average and dtype.is_type("MONEY")) else "UNKNOWN"
    if dialect in {"tsql", "fabric", "redshift"}:
        if parts:
            return f"DECIMAL(38, {max(parts[1], 6) if average and dialect != 'redshift' else parts[1]})"
        if integer:
            return "BIGINT" if dialect == "redshift" or dtype.is_type("BIGINT") else "INT"
        if floating:
            return "DOUBLE"
        return dtype.copy() if dtype.is_type("MONEY", "SMALLMONEY") and dialect != "redshift" else "UNKNOWN"
    if dialect == "duckdb":
        if average and (integer or floating or decimal or dtype.is_type("HUGEINT", "UBIGINT")):
            return "DOUBLE"
        if parts:
            return f"DECIMAL(38, {parts[1]})"
        if integer or dtype.is_type("HUGEINT", "UBIGINT"):
            return "HUGEINT"
        return "DOUBLE" if floating else "UNKNOWN"
    if dialect in {"spark", "databricks"}:
        if parts:
            precision, scale = parts
            if average:
                if dialect == "databricks":
                    return f"DECIMAL({min(precision + 4, 38)}, {scale + min(4, 38 - precision)})"
                return f"DECIMAL({min(precision + 4, 38)}, {min(scale + 4, 38)})"
            # Databricks' current documentation caps the precision differently
            # from Spark 3.5. Only their unambiguous common range is certified.
            if dialect == "databricks" and precision > 21:
                return "UNKNOWN"
            return f"DECIMAL({min(precision + 10, 38)}, {scale})"
        if integer:
            return "DOUBLE" if average else "BIGINT"
        return "DOUBLE" if floating else "UNKNOWN"
    return "UNKNOWN"


def _postgres_statistical_type(node, dialect):
    dtype = _argument_type(node)
    if dtype and dtype.is_type("TINYINT", "SMALLINT", "INT", "BIGINT", "DECIMAL"):
        return "NUMERIC"
    return "DOUBLE" if dtype and dtype.is_type("FLOAT", "DOUBLE") else "UNKNOWN"


def _percentile_type(node, dialect):
    dtype = _argument_type(node)
    # The scalar percentile overload returns x's type. The array-percentiles
    # overload instead returns ARRAY(x), so do not apply the scalar rule to it.
    quantile = node.args.get("quantile")
    if (dtype is None or dtype.is_type("UNKNOWN", "NULL")
            or quantile is None or not quantile.type or quantile.type.is_type("UNKNOWN", "NULL")):
        return "UNKNOWN"
    if dialect == "trino" and not dtype.is_type("BIGINT", "FLOAT", "DOUBLE"):
        return "UNKNOWN"  # Narrower integers require overload-specific coercion evidence.
    if quantile.type.is_type("ARRAY"):
        return exp.DataType(this=exp.DType.ARRAY, expressions=[dtype.copy()], nested=True)
    return dtype.copy()


def _number_type(node, dialect):
    values = []
    for name, default in (("precision", 38), ("scale", 0)):
        value = node.args.get(name)
        if value is None:
            values.append(default)
        elif isinstance(value, exp.Literal) and not value.is_string and value.this.isdigit():
            values.append(int(value.this))
        else:
            return "UNKNOWN"
    precision, scale = values
    return f"DECIMAL({precision}, {scale})" if 1 <= precision <= 38 and 0 <= scale <= precision else "UNKNOWN"


def _duckdb_percentile_type(node, dialect):
    dtype = _argument_type(node)
    if dtype and dtype.is_type("SMALLINT", "INT", "BIGINT", "HUGEINT", "FLOAT", "DOUBLE"):
        return _percentile_type(node, dialect)
    return "UNKNOWN"  # Decimal binding is not a simple element-type identity.


def _duckdb_repeat_type(node, dialect):
    dtype = _argument_type(node)
    return dtype.copy() if dtype and dtype.is_type("VARCHAR", "VARBINARY", "ARRAY") else "UNKNOWN"


def _duckdb_json_string_type(node, dialect):
    path = node.args.get("expression")
    if isinstance(path, exp.JSONPath):
        return "VARCHAR"
    dtype = path.type if isinstance(path, exp.Expr) else None
    if dtype and dtype.is_type("ARRAY") and dtype.expressions and dtype.expressions[0].is_type("VARCHAR"):
        return "VARCHAR[]"
    return "VARCHAR" if dtype and dtype.is_type("VARCHAR", "TINYINT", "SMALLINT", "INT", "BIGINT", "UBIGINT") else "UNKNOWN"


def _duckdb_round_type(node, dialect):
    dtype = _argument_type(node)
    return dtype.copy() if dtype and dtype.is_type("TINYINT", "SMALLINT", "INT", "BIGINT", "HUGEINT", "FLOAT", "DOUBLE") else "UNKNOWN"


# Per-call rules share the same annotation path as fixed native repairs. They
# neither replace native nodes nor alter SQLGlot's global metadata registries.
NATIVE_TYPE_RULES = {
    dialect: {exp.Sum: _aggregate_type, exp.Avg: _aggregate_type}
    for dialect in ("postgres", "duckdb", "tsql", "fabric", "redshift", "spark", "databricks")
}
NATIVE_TYPE_RULES["postgres"].update({
    cls: _postgres_statistical_type for cls in
    (exp.Stddev, exp.StddevPop, exp.StddevSamp, exp.Variance, exp.VariancePop)
})
NATIVE_TYPE_RULES["trino"] = {exp.ApproxQuantile: _percentile_type}
NATIVE_TYPE_RULES["snowflake"] = {exp.ToNumber: _number_type}
NATIVE_TYPE_RULES["duckdb"].update({exp.ApproxQuantile: _duckdb_percentile_type, exp.Repeat: _duckdb_repeat_type,
                                   exp.JSONExtractScalar: _duckdb_json_string_type, exp.Round: _duckdb_round_type})


def inferred_types(tree, schema, dialect):
    tree = recognize_functions(tree.copy(), dialect)
    if has_generators(tree):
        return {}  # A SELECT item need not correspond to one output column.
    metadata = dict(Dialect.get_or_raise(dialect).EXPRESSION_METADATA)
    key = dialect.partition(",")[0].strip().lower()
    for node_type, returns in NATIVE_RETURN_TYPES.get(key, {}).items():
        metadata[node_type] = {"returns": exp.DataType.build(returns, dialect=dialect)}
    for node_type, rule in NATIVE_TYPE_RULES.get(key, {}).items():
        def dependent(annotator, node, rule=rule):
            result = rule(node, key)
            node.type = result if isinstance(result, exp.DataType) else exp.DataType.build(result, dialect=dialect)
        metadata[node_type] = {"annotator": dependent}
    native = metadata.get(exp.Anonymous, {})

    def anonymous(annotator, node):
        spec = function_spec(node, dialect)
        if spec:
            node.type = exp.DataType.build(spec.returns or "UNKNOWN", dialect=dialect)
        elif native.get("annotator"):
            native["annotator"](annotator, node)
        else:
            node.type = exp.DataType.build(native.get("returns") or "UNKNOWN")

    metadata[exp.Anonymous] = {"annotator": anonymous}
    typed = annotate_types(tree, schema=schema, dialect=dialect, expression_metadata=metadata)
    return {p.output_name: sql(p.type, dialect) for p in typed.selects
            if not p.is_star and p.type and p.type.this not in {exp.DataType.Type.UNKNOWN, exp.DataType.Type.NULL}}
