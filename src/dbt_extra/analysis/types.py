"""Best-effort type inference from qualified SQL and declared schema evidence."""

from sqlglot import Dialect, exp
from sqlglot.optimizer.annotate_types import annotate_types

from dbt_extra.sql.renderer import sql
from dbt_extra.sql.functions import function_spec, has_generators, recognize_functions


def inferred_types(tree, schema, dialect):
    tree = recognize_functions(tree.copy(), dialect)
    if has_generators(tree):
        return {}  # A SELECT item need not correspond to one output column.
    metadata = dict(Dialect.get_or_raise(dialect).EXPRESSION_METADATA)
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
