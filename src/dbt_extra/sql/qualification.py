"""Qualification for authored rewrites: unknown columns are not absent columns."""

from inspect import signature

from sqlglot import exp, parse_one
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.qualify_tables import qualify_tables
from sqlglot.optimizer.scope import Scope, traverse_scope
from sqlglot.schema import MappingSchema, ensure_schema

from dbt_extra.errors import SpecError


# SQLGlot 30.24 removed this option; 30.8 needs it for unknown single inputs
# alongside known schemas. Our own guard always rejects ambiguous inference.
INFER_SCHEMA_OPTIONS = {"infer_schema": True} if "infer_schema" in signature(qualify).parameters else {}


class SourceSchema(MappingSchema):
    """Native normalized lookup plus original ordered column identifiers."""

    def __init__(self, mapping=None, *, dialect):
        super().__init__(mapping, dialect=dialect)

        def spellings(value):
            return {key: spellings(item) if isinstance(item, dict)
                    else parse_one(key, read=dialect, into=exp.Identifier)
                    for key, item in value.items()}

        self.spellings = MappingSchema(spellings(mapping or {}), dialect=dialect)

    def add_table(self, table, column_mapping=None, **kwargs):
        super().add_table(table, column_mapping, **kwargs)
        self.spellings.add_table(table, {
            name: parse_one(name, read=self.dialect, into=exp.Identifier)
            for name in (column_mapping or {})
        }, **kwargs)


def source_schema(schema, dialect):
    return SourceSchema(schema, dialect=dialect) if schema is None or isinstance(schema, dict) else ensure_schema(schema, dialect=dialect)


def bind_single_inputs(tree, schema, dialect):
    """Replace removed native single-table inference, without inventing schemas.

    Authored callers must run check_bindings first. Inspection is separately
    best-effort and historically enabled native inference for these inputs.
    """
    if INFER_SCHEMA_OPTIONS:
        return tree
    schema = ensure_schema(schema or {}, dialect=dialect)
    tree = qualify_tables(normalize_identifiers(tree.copy(), dialect=dialect,
                          store_original_column_identifiers=True), dialect=dialect)
    for scope in traverse_scope(tree):
        inputs = list(scope.selected_sources.items())
        if len(inputs) == 1:
            alias, (_, source) = inputs[0]
            if isinstance(source, exp.Table) and not schema.column_names(source):
                for column in scope.columns:
                    if not column.table:
                        column.set("table", exp.to_identifier(alias))
    return tree


def remember_schema_outputs(tree, schema):
    for scope in traverse_scope(tree):
        for column in scope.columns:
            if "extra_spelling" in column.this.meta:
                continue
            source = scope.sources.get(column.table)
            identifier = None
            if isinstance(source, exp.Table) and hasattr(schema, "spellings"):
                identifier = (schema.spellings.find(source) or {}).get(column.name)
            elif isinstance(source, Scope):
                for projection in source.expression.selects:
                    if projection.output_name == column.name:
                        identifier = projection.args.get("alias") if isinstance(projection, exp.Alias) else projection.this
                        break
            if isinstance(identifier, exp.Identifier):
                column.this.meta["extra_spelling"] = identifier.meta.get("extra_spelling", dict(identifier.args))
        for projection in scope.expression.selects:
            if isinstance(projection, exp.Alias) and isinstance(projection.this, exp.Column):
                alias = projection.args["alias"]
                spelling = projection.this.this.meta.get("extra_spelling")
                if "extra_spelling" not in alias.meta and spelling:
                    alias.meta["extra_spelling"] = spelling


def check_bindings(tree, schema, dialect, *, strict=True):
    schema = source_schema(schema, dialect)
    outputs_known = {}
    for scope in traverse_scope(tree):
        inputs = [source for _, source in scope.selected_sources.values()]
        unknown = any(
            (isinstance(source, exp.Table) and not schema.column_names(source))
            or (isinstance(source, Scope) and not outputs_known.get(id(source), False))
            for source in inputs
        )
        if len(inputs) > 1 and unknown and (
            any(not c.table for c in scope.columns)
            or any(j.args.get("using") or j.method == "NATURAL" for j in scope.expression.find_all(exp.Join))
        ):
            raise SpecError("Unqualified columns or USING/NATURAL join with unknown joined schema; provide complete input schemas")
        if strict and unknown and any(p.is_star for p in scope.expression.selects):
            raise SpecError("Cannot expand projection star without complete ordered input schemas (documentation columns are partial)")
        outputs_known[id(scope)] = not unknown or not any(p.is_star for p in scope.expression.selects)
        if not strict:
            continue
        for projection in scope.expression.selects:
            for star in projection.find_all(exp.Star):
                if isinstance(star.parent, exp.Count):
                    continue
                if not projection.is_star or any(value for key, value in star.args.items()
                                                 if key not in {"except_", "replace"}):
                    raise SpecError("Unsupported projection star modifier; model unchanged")
        if any(c.table and c.table not in scope.sources for c in scope.external_columns):
            raise SpecError("Correlated queries are not eligible for authored optimization")
        if scope.can_be_correlated and unknown and any(not c.table for c in scope.columns):
            raise SpecError("Cannot resolve possible correlated columns without complete input schemas")
        names = []
        for projection in scope.expression.selects:
            if projection.is_star or not projection.output_name:
                continue
            identifier = projection.args.get("alias") if isinstance(projection, exp.Alias) else projection.this
            names.append(normalize_identifiers(identifier.copy(), dialect=dialect).name
                         if isinstance(identifier, exp.Identifier) else projection.output_name)
        if len(names) != len(set(names)):
            raise SpecError("Duplicate output names prevent safe source qualification")
    return schema


def qualify_source(tree, schema, dialect):
    schema = check_bindings(tree, schema, dialect)
    qualified = qualify(
        bind_single_inputs(tree.copy(), schema, dialect), dialect=dialect, schema=schema, **INFER_SCHEMA_OPTIONS,
        validate_qualify_columns=True, quote_identifiers=True, identify=False,
    )
    if any(p.is_star for scope in traverse_scope(qualified) for p in scope.expression.selects):
        raise SpecError("Projection star could not be completely expanded")
    check_bindings(qualified, schema, dialect)
    return qualified
