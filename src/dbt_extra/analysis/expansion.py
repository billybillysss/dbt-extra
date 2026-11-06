"""Expand authored upstream definitions with operation-local evidence and caches."""

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope

from dbt_extra.analysis.column_demand import ColumnDemand
from dbt_extra.errors import SpecError
from dbt_extra.project.model_sql import parse_model
from dbt_extra.project.references import resolve_ref
from dbt_extra.project.schema_evidence import SourceSchemas
from dbt_extra.sql.functions import has_generators
from dbt_extra.sql.safety import has_evaluation_barrier


class ModelExpansion:
    def __init__(self, project, outcomes, *, boundaries=(), expanded=True):
        self.project = project
        self.outcomes = outcomes
        self.boundaries = set(boundaries)
        self.expanded = expanded
        self.refs, self.macros = {}, {}
        self.parsed_cache, self.expansion_cache = {}, {}
        self.evidence = SourceSchemas(project, parse=self.parsed) if expanded else SourceSchemas(project)
        self.demand = ColumnDemand(self.parsed, self.evidence, project.require_dialect(),
                                   lambda ref: resolve_ref(project, ref))

    def parsed(self, resource):
        if resource.id not in self.parsed_cache:
            try:
                self.parsed_cache[resource.id] = parse_model(self.project, resource.code, resource.id, expand=self.expanded)
            except SpecError as exc:
                self.parsed_cache[resource.id] = exc
        value = self.parsed_cache[resource.id]
        if isinstance(value, SpecError):
            raise value
        return value

    def validate_boundaries(self, resource):
        visited = set()

        def reachable(current):
            if current.id in visited:
                return
            visited.add(current.id)
            try:
                value = self.parsed(current)
            except SpecError:
                return
            for ref in value.refs.values():
                upstream = resolve_ref(self.project, ref)
                if upstream:
                    reachable(upstream)

        reachable(resource)
        invalid = self.boundaries - (visited - {resource.id})
        if invalid:
            raise SpecError(f"--from models are not upstream dependencies: {', '.join(sorted(invalid))}")

    def expand(self, resource, active=(), wanted=None):
        if resource.id in active:
            raise SpecError(f"Cyclic SQL expansion: {' -> '.join((*active, resource.id))}")
        key = (resource.id, tuple(wanted or ()))
        if key in self.expansion_cache:
            cached, diagnostics = self.expansion_cache[key]
            for item in diagnostics:
                self.outcomes.add(item["rule"], item["scope"], item["status"], item["reason_code"], item["reason"],
                                  resource=item["resource_id"], count=item["occurrence_count"])
            return cached.copy()
        issues = self.outcomes.values
        counts = {id(item): item.get("occurrence_count", 1) for item in issues}
        value = self.parsed(resource)
        self.refs.update(value.refs)
        self.macros.update(value.macros)
        tree, requirements = self.demand.for_resource(resource, wanted)
        for scope in list(traverse_scope(tree)):
            for table in list(scope.tables):
                if isinstance(scope.sources.get(table.alias_or_name), Scope):
                    continue
                ref = value.refs.get(table.name)
                if not ref:
                    continue
                if ref.kind == "this":
                    table.meta["extra_owner"] = resource.id
                upstream = resolve_ref(self.project, ref)
                reason, replacement = None, None
                if not self.expanded:
                    reason = "expansion disabled"
                elif upstream is None:
                    reason = "stored self relation" if ref.kind == "this" else "unresolved relation"
                elif upstream.id in self.boundaries:
                    reason = "explicit boundary"
                elif upstream.kind != "model" or (upstream.path and upstream.path.suffix == ".py"):
                    reason = upstream.kind + " input"
                elif upstream.path is None:
                    reason = "artifact/package-only definition; authored local source unavailable"
                else:
                    try:
                        up = self.parsed(upstream)
                        materialized = up.config.get("materialized", upstream.config.get("materialized", "view"))
                        if up.config_dynamic:
                            reason = "dynamic configuration; materialization cannot be established offline"
                        elif materialized not in {"view", "table", "ephemeral"}:
                            reason = f"{materialized} materialization"
                        elif has_evaluation_barrier(up.tree) or has_generators(up.tree):
                            reason = "volatile, unknown or generator function"
                        else:
                            replacement = self.expand(upstream, (*active, resource.id), requirements.get(table.name))
                    except SpecError as exc:
                        reason = str(exc)
                if replacement is None:
                    self.outcomes.add("expansion", "resource", "blocked", "expansion_boundary", reason,
                                      resource=upstream.id if upstream else ref.text)
                    continue
                modifiers = {k for k, v in table.args.items() if v is not None} - {"this", "db", "catalog", "alias"}
                if modifiers:
                    self.outcomes.add("expansion", "resource", "blocked", "relation_modifiers",
                                      f"Cannot expand relation modifiers: {', '.join(sorted(modifiers))}",
                                      resource=upstream.id)
                    continue
                alias = table.args.get("alias") or exp.TableAlias(this=exp.to_identifier(table.name))
                table.replace(exp.Subquery(this=replacement, alias=alias.copy()))
        diagnostics = [{**item, "occurrence_count": item.get("occurrence_count", 1) - counts.get(id(item), 0)}
                       for item in issues if item.get("occurrence_count", 1) > counts.get(id(item), 0)]
        self.expansion_cache[key] = tree.copy(), diagnostics
        return tree
