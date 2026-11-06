"""SQLGlot dialect resolution and narrowly proven source-rewrite permissions."""

from sqlglot.dialects import Dialect

from dbt_extra.errors import SpecError


# Only adapter names that differ from their SQLGlot dialect belong here.
# Fabric Warehouse has its own dialect: never collapse it to T-SQL.
ADAPTER_DIALECTS = {"fabricspark": "spark", "sqlserver": "tsql"}

# These permissions are independent of parser support and dialect inheritance.
# New dialects stay excluded until their arithmetic semantics are tested.
INTEGER_LITERAL_FOLD_DIALECTS = frozenset({"duckdb", "postgres", "spark", "tsql", "bigquery"})
INTEGER_ADD_ZERO_DIALECTS = frozenset({"duckdb"})
# Membership and equality can have different implicit-cast rules. This permission
# additionally requires identical, declared base-column integral types.
INTEGER_MEMBERSHIP_DIALECTS = frozenset({"duckdb", "spark"})


def validate_dialect(value):
    """Return a validated SQLGlot name, retaining any explicit dialect settings."""
    if not isinstance(value, str) or not value.strip():
        raise SpecError("SQL analysis requires an explicit SQLGlot dialect name")
    name, separator, settings = value.partition(",")
    dialect = name.strip().lower() + separator + settings
    if not name.strip():
        raise SpecError("SQL analysis requires an explicit SQLGlot dialect name")
    try:
        Dialect.get_or_raise(dialect)
    except ValueError as exc:
        raise SpecError(f"Invalid SQL dialect {value!r}: {exc}; use a SQLGlot dialect name") from exc
    return dialect


def resolve_dialect(value="auto", *, adapter=None):
    """Resolve an explicit choice or manifest adapter, never guessing generic SQL."""
    if value != "auto":
        return validate_dialect(value)
    if adapter is None or adapter == "":
        return None
    if not isinstance(adapter, str):
        raise SpecError("Manifest adapter_type must be a string; set --dialect or analysis.dialect explicitly")
    try:
        return validate_dialect(ADAPTER_DIALECTS.get(adapter, adapter))
    except SpecError as exc:
        raise SpecError(f"Cannot resolve SQL dialect for manifest adapter {adapter!r}; "
                        f"set --dialect or analysis.dialect explicitly: {exc}") from exc
