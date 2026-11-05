"""Conservative qualification and direct column lineage."""

from sqlglot import exp, parse_one
from sqlglot.lineage import lineage
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import build_scope
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

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

    def normalized(name):
        return normalize_identifiers(parse_one(name, read=dialect, into=exp.Identifier), dialect=dialect).name

    relations = {normalized(token): resource for token, resource in dependencies.items()}
    relations.update(dependencies)  # Quoted relation placeholders retain their case.
    columns = {normalized(token): {normalized(name): name for name in names}
               for token, names in schema.items()}

    def for_column(name):
        # The tree is already qualified: do not normalize a quoted output name
        # again as an unquoted string (Snowflake would uppercase it).
        graph = lineage(exp.column(name, quoted=True), tree, schema=schema, dialect=dialect,
                        scope=scope, trim_selects=False)
        leaves = []
        for node in graph.walk():
            if not node.downstream and isinstance(node.expression, exp.Table):
                token = node.expression.name
                relation = relations.get(token, sql(node.expression, dialect))
                column = node.name.rsplit(".", 1)[-1].strip('"`[]')
                column = columns.get(token, {}).get(column, column)
                leaves.append({"resource_id": relation, "column": column})
        return leaves

    return for_column
