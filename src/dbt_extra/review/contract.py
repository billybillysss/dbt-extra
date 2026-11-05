"""Review table identities, editability, and portable cell representations."""

import json

from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import literal, mapping


HEADERS = {
    "resources": ["resource_id", "package", "model_path", "name", "resource_type", "source_file", "description", "properties", "sql", "status", "reason"],
    "columns": ["resource_id", "package", "model_path", "name", "column", "expression", "description", "data_type", "properties", "upstream_columns", "status"],
}
EDITABLE = {"resources": {"description", "properties", "sql"}, "columns": {"expression", "description", "data_type", "properties"}}
LEGEND = [
    ["dbt-extra dbt review", "dbt files remain the source of truth; no warehouse or dbt execution."],
    ["Editable fields", "Description, properties, SQL and supported expressions. Identity, model_path, file paths, status, and lineage are read-only."],
    ["properties", 'JSON object for other authored metadata, e.g. {"data_tests": ["not_null"]}. Never resolved/inherited config.'],
    ["Metadata destination", "Existing dbt YAML resource entries only. Missing entries are reported and skipped; no properties file is created."],
    ["sql / expression", "Edit full authored SQL OR individual output expressions, not both for the same resource."],
    ["Blank values", "Clear a field. Removing rows, renaming/moving resources, and new resource creation are not supported."],
    ["Safety", "Import rejects stale source/property files, unknown identities, formulas, and edits to read-only fields."],
    ["Example (not imported)", 'column: customer_id; description: Customer identifier; data_type: bigint; properties: {"data_tests": ["not_null"]}'],
    ["Limitations", "Opaque Jinja can be edited as full source but not automatically rewritten; use dbt parse/build independently."],
]


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def cell_text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SpecError("Review cells must be text; use literal JSON for structured fields")
    return value


def structured(value, context, forbidden=()):
    try:
        result = mapping(json.loads(value or "{}"), context)
        literal(result, context)
    except ValueError as exc:
        raise SpecError(f"{context}: invalid JSON object: {exc}") from exc
    if result.keys() & set(forbidden):
        raise SpecError(f"{context}: fields have dedicated cells: {', '.join(forbidden)}")
    return result


def key_for(name, row):
    return (row["resource_id"], row["column"]) if name == "columns" else row["resource_id"]
