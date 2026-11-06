"""Propagate all-consumer column demand through proven model interfaces."""

from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.scope import traverse_scope

from dbt_extra.errors import SpecError
from dbt_extra.sql.qualification import qualify_source
from dbt_extra.sql.rewrites.projections import prune_projections


class ColumnDemand:
    def __init__(self, parse, evidence, dialect, resolve):
        self.parse = parse
        self.evidence = evidence
        self.dialect = dialect
        self.resolve = resolve
        self.cache = {}

    def for_resource(self, resource, wanted):
        key = (resource.id, tuple(wanted or ()))
        if key in self.cache:
            query, requirements = self.cache[key]
            return query.copy(), requirements
        original = self.parse(resource)
        query, requirements = original.tree.copy(), {}
        if wanted:
            try:
                bound = qualify_source(query, self.evidence.for_parsed(original), self.dialect)
                names = {p.output_name for p in bound.selects}
                requested = [n if n in names else normalize_identifiers(exp.to_identifier(n), dialect=self.dialect).name for n in wanted]
                if all(n in names for n in requested):
                    wrapper = exp.select(*(exp.column(n, table="extra_demand", quoted=True) for n in requested)).from_(
                        bound.subquery("extra_demand"))
                    prune_projections(wrapper, dialect=self.dialect)
                    query = wrapper.args["from_"].this.this.copy()
                    for scope in traverse_scope(query):
                        for column in scope.columns:
                            source = scope.sources.get(column.table)
                            if isinstance(source, exp.Table) and source.name in original.refs:
                                upstream = self.resolve(original.refs[source.name])
                                if upstream and self.evidence.for_resource(upstream).complete:
                                    requirements.setdefault(source.name, set()).add(column.name)
            except (SpecError, SqlglotError):
                query, requirements = original.tree.copy(), {}
        self.cache[key] = query.copy(), {k: tuple(sorted(v)) for k, v in requirements.items()}
        return query, self.cache[key][1]
