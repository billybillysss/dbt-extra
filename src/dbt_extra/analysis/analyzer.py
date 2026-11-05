"""Shared best-effort dbt source analysis with explicit coverage and provenance."""

from __future__ import annotations

from sqlglot import exp
from sqlglot.errors import SqlglotError
from dbt_extra.analysis.lineage import column_lineage, qualify_columns
from dbt_extra.analysis.models import ResourceAnalysis, coverage
from dbt_extra.analysis.types import inferred_types
from dbt_extra.sql.macros import macro_calls, parse_model, contains_opaque
from dbt_extra.sql.references import resolve_ref
from dbt_extra.errors import SpecError
from dbt_extra.sql.scopes import relation_tables
from dbt_extra.sql.renderer import sql, render


def analyze(project, resource, *, expand=False) -> ResourceAnalysis:
    result = {"resource_id": resource.id, "name": resource.name, "resource_type": resource.kind,
              "package": resource.package, "model_path": resource.model_path, "source_file": resource.source_file,
              "properties_file": resource.property_path.relative_to(project.root).as_posix() if resource.property_path else None,
              "description": resource.properties.get("description", ""), "properties": resource.properties,
              "config": resource.config, "sql": resource.code, "columns": [], "dependencies": [],
              "status": "metadata_only", "reason": None, "provenance": "authored" if resource.path else "artifact"}
    declared = resource.columns
    outputs = {name: {"name": name, "expression": "", "description": props.get("description", ""),
                      "data_type": props.get("data_type", ""), "properties": props,
                      "upstream_columns": [], "status": "declared", "provenance": "authored" if resource.property_path else "artifact"}
               for name, props in declared.items()}
    if resource.kind == "model" and (not resource.path or resource.path.suffix == ".sql"):
        try:
            dialect = project.require_dialect()
            parsed = parse_model(project, resource.code, resource.id, expand=expand, partial=True)
            provenance = "expanded_macro_sql" if expand and macro_calls(resource.code) else "authored_sql"
            result["config"] = {**result["config"], **parsed.config}
            result["status"] = "parsed"
            if parsed.opaque_macros:
                result["status"], result["reason"] = "partial", "; ".join(dict.fromkeys(parsed.opaque_macros.values()))
            dependencies = {}
            schema = {}
            for token, ref in parsed.refs.items():
                upstream = resolve_ref(project, ref)
                dependencies[token] = upstream.id if upstream else ref.text
                if upstream:
                    if upstream.known_columns:
                        schema[token] = {name: p.get("data_type") or "UNKNOWN" for name, p in upstream.known_columns.items()}
            result["dependencies"] = list(dict.fromkeys(dependencies.values()))
            result["context"] = {"query": resource.code, "relations": [sql(t, dialect) for t in relation_tables(parsed.tree)],
                                 "note": "Expressions depend on complete query context, including joins, filters, grouping and multiplicity"}
            projections = parsed.tree.selects
            counts = {}
            for p in projections:
                counts[p.output_name] = counts.get(p.output_name, 0) + 1
            for projection in projections:
                if contains_opaque(projection, parsed):
                    continue  # A template boundary may emit any number of columns.
                name = projection.output_name
                if not name or projection.is_star or counts[name] != 1:
                    result["status"], result["reason"] = "partial", "Wildcard, unnamed, or duplicate output columns require additional schema evidence"
                    continue
                item = outputs.setdefault(name, {"name": name, "description": "", "data_type": "", "properties": {}, "upstream_columns": []})
                expression = projection.this if isinstance(projection, exp.Alias) else projection
                expression_text = render(expression, parsed, dialect, pretty=False).strip().rstrip(";")
                # Template relations in scalar subqueries remain readable; expression
                # writeback itself is restricted to independently parseable expressions.
                item.update(expression=expression_text, status="parsed", provenance=provenance)
            # Unknown shapes cannot supply schema/type/lineage evidence. Keep
            # independently parsed expressions, without qualifying through them.
            if not parsed.opaque_macros:
                try:
                    qualified = qualify_columns(parsed.tree, schema, dialect)
                    for projection in qualified.selects:
                        name = projection.output_name
                        if name and not projection.is_star and name not in outputs:
                            expression = projection.this if isinstance(projection, exp.Alias) else projection
                            outputs[name] = {"name": name, "description": "", "data_type": "", "properties": {},
                                "upstream_columns": [], "expression": render(expression, parsed, dialect, pretty=False).strip().rstrip(";"), "status": "parsed", "provenance": provenance}
                    if not any(p.is_star for p in qualified.selects) and result["reason"] == "Wildcard, unnamed, or duplicate output columns require additional schema evidence":
                        result["status"], result["reason"] = "parsed", None
                    types = inferred_types(qualified, schema, dialect)
                    lineage_for = column_lineage(qualified, schema, dialect, dependencies)
                    output_names = {p.output_name for p in qualified.selects if not p.is_star}
                    for name, item in outputs.items():
                        if name not in output_names:
                            continue
                        if name in types:
                            item["inferred_type"] = types[name]
                        leaves = lineage_for(name)
                        item["upstream_columns"] = leaves
                        item["status"] = "resolved" if leaves else "parsed"
                except (SqlglotError, ValueError, KeyError) as exc:
                    result["status"], result["reason"] = "partial", f"Column qualification unavailable: {exc}"
        except (SpecError, SqlglotError) as exc:
            result["status"], result["reason"] = "unavailable", str(exc)
    elif resource.kind == "macro":
        result["status"], result["reason"] = "source_only", "Macro files are editable source, not expanded SQL"
    elif resource.kind == "snapshot":
        result["reason"] = "Snapshots retain their execution/history boundary"
    if not resource.path:
        result["reason"] = "Artifact/package resource is read-only; source freshness is unverified"
    result["columns"] = list(outputs.values())
    return result


def catalog(project, resources, *, expand=False):
    models = [analyze(project, resource, expand=expand) for resource in resources]
    return {"format_version": 1, "project": project.name, "dialect": project.dialect,
            "source_of_truth": "dbt", "resources": models, "diagnostics": project.diagnostics,
            "artifact_evidence": {"manifest": str(project.manifest_path) if project.manifest else None,
                                  "generated_at": project.manifest.get("metadata", {}).get("generated_at"),
                                  "compiled_sql_used_for_rewriting": False},
            "coverage": coverage(models)}
