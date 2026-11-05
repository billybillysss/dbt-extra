"""Best-effort type inference from qualified SQL and declared schema evidence."""

from sqlglot import exp
from sqlglot.optimizer.annotate_types import annotate_types

from dbt_extra.sql.renderer import sql


def inferred_types(tree, schema, dialect):
    typed = annotate_types(tree, schema=schema, dialect=dialect)
    return {p.output_name: sql(p.type, dialect) for p in typed.selects
            if not p.is_star and p.type and p.type.this not in {exp.DataType.Type.UNKNOWN, exp.DataType.Type.NULL}}
