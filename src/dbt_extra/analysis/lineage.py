"""Conservative qualification and direct column lineage."""

from sqlglot import exp
from sqlglot.lineage import lineage
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import build_scope

from dbt_extra.errors import SpecError
from dbt_extra.sql.qualification import bind_single_inputs, check_bindings
from dbt_extra.sql.renderer import sql


def qualify_columns(tree, schema, dialect):
    try:
        schema = check_bindings(tree, schema, dialect, strict=False)
    except SpecError as exc:
        raise ValueError(str(exc)) from exc
    return qualify(bind_single_inputs(tree.copy(), schema, dialect), dialect=dialect,
                   schema=schema, validate_qualify_columns=True)


def column_lineage(tree, schema, dialect, dependencies):
    scope = build_scope(tree)

    def for_column(name):
        graph = lineage(name, tree, schema=schema, dialect=dialect, scope=scope, trim_selects=False)
        leaves = []
        for node in graph.walk():
            if not node.downstream and isinstance(node.expression, exp.Table):
                relation = dependencies.get(node.expression.name, sql(node.expression, dialect))
                column = node.name.rsplit(".", 1)[-1].strip('"`[]')
                leaves.append({"resource_id": relation, "column": column})
        return leaves

    return for_column
