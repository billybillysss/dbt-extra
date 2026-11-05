"""Operation-local, ordered schema evidence, separate from documentation lineage.

Only supported authored query outputs are complete. Catalogs lack a verifiable
warehouse freshness contract here; neither they nor YAML/manifest descriptions
are used as exhaustive relation schemas.
"""

from dataclasses import dataclass

from sqlglot import exp
from sqlglot.errors import SqlglotError

from dbt_extra.errors import SpecError
from dbt_extra.sql.macros import parse_model
from dbt_extra.sql.qualification import SourceSchema, qualify_source, remember_schema_outputs
from dbt_extra.sql.references import resolve_ref
from dbt_extra.sql.source_rules import remember_identifiers, remember_outputs, restore_identifiers


@dataclass(frozen=True)
class SchemaColumn:
    name: str
    quoted: bool = False
    data_type: str = "UNKNOWN"


@dataclass(frozen=True)
class RelationEvidence:
    resource_id: str
    columns: tuple[SchemaColumn, ...] = ()
    complete: bool = False
    provenance: str = "unknown"
    freshness: str = "unverified"


class SourceSchemas:
    def __init__(self, project):
        self.project = project
        self.cache = {}
        self.active = []

    def for_parsed(self, parsed):
        schema = SourceSchema(dialect=self.project.require_dialect())
        for token, ref in parsed.refs.items():
            resource = resolve_ref(self.project, ref)
            if resource is None:
                continue
            evidence = self.for_resource(resource)
            if evidence.complete:
                schema.add_table(exp.Table(this=exp.to_identifier(token, quoted=True)), {
                    exp.to_identifier(c.name, quoted=c.quoted).sql(dialect=self.project.require_dialect()): c.data_type
                    for c in evidence.columns
                })
        return schema

    def for_resource(self, resource):
        if resource.id in self.active:
            raise SpecError("Schema dependency cycle: " + " -> ".join([*self.active, resource.id]))
        if resource.id in self.cache:
            return self.cache[resource.id]
        evidence = RelationEvidence(resource.id, provenance="partial documentation or unverifiable artifact")
        if resource.kind == "model" and resource.path and resource.path.suffix == ".sql":
            self.active.append(resource.id)
            try:
                parsed = parse_model(self.project, resource.code, resource.id, expand=True)
                if any(not p.output_name for p in parsed.tree.selects):
                    raise SpecError("Unnamed outputs are not complete schema evidence")
                schema = self.for_parsed(parsed)
                remember_identifiers(parsed.tree)
                qualified = qualify_source(parsed.tree, schema, self.project.require_dialect())
                remember_schema_outputs(qualified, schema)
                remember_outputs(qualified)
                restore_identifiers(qualified)
                columns = []
                for projection in qualified.selects:
                    identifier = projection.args.get("alias") if isinstance(projection, exp.Alias) else projection.this
                    if not isinstance(identifier, exp.Identifier):
                        raise SpecError("Unresolved output name")
                    columns.append(SchemaColumn(identifier.name, bool(identifier.args.get("quoted"))))
                evidence = RelationEvidence(resource.id, tuple(columns), True, "authored query outputs", "operation snapshot")
            except (SqlglotError, KeyError) as exc:
                raise SpecError(f"Cannot infer schema for {resource.id}: {exc}") from exc
            except SpecError as exc:
                if "Schema dependency cycle:" in str(exc):
                    raise
                evidence = RelationEvidence(resource.id, provenance=str(exc))
            finally:
                self.active.pop()
        self.cache[resource.id] = evidence
        return evidence
