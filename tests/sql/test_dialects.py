"""Dialect availability is separate from permission to rewrite arithmetic."""

import pytest
from sqlglot import exp
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

from dbt_extra.errors import SpecError
from dbt_extra.sql.rewrites.engine import optimize_source
from dbt_extra.sql.dialects import resolve_dialect, validate_dialect
from dbt_extra.sql.parser import parse_authored


@pytest.mark.parametrize("value", [None, "", " ", ", normalization_strategy=case_sensitive", 123, {}])
def test_missing_name_never_selects_sqlglot_generic_dialect(value):
    with pytest.raises(SpecError, match="explicit SQLGlot dialect name"):
        validate_dialect(value)


@pytest.mark.parametrize("value", ["not_a_dialect", "fabricspark", "sqlserver", "auto"])
def test_explicit_values_are_sqlglot_names_not_adapter_aliases(value):
    with pytest.raises(SpecError, match="Invalid SQL dialect"):
        validate_dialect(value)


def test_normalization_retains_explicit_sqlglot_settings():
    dialect = validate_dialect(" SPARK , normalization_strategy=case_sensitive")
    assert dialect == "spark, normalization_strategy=case_sensitive"
    assert normalize_identifiers(exp.column("MixedCase"), dialect=dialect).name == "MixedCase"


def test_fabric_keeps_its_own_identifier_semantics_not_tsql_semantics():
    dialect = resolve_dialect(adapter="fabric")
    assert dialect == "fabric"
    assert normalize_identifiers(exp.column("MixedCase"), dialect=dialect).name == "MixedCase"
    assert normalize_identifiers(exp.column("MixedCase"), dialect="tsql").name == "mixedcase"


@pytest.mark.parametrize("dialect", ["fabric", "databricks", "snowflake", "redshift"])
def test_related_or_unverified_dialects_do_not_inherit_arithmetic_permissions(dialect):
    candidate = optimize_source("select 1+2 as n, t.amount+0 as amount from t", dialect,
                                schema={"t": {"amount": "INT"}})
    assert len(list(parse_authored(candidate, dialect).tree.find_all(exp.Add))) == 2
    assert optimize_source(candidate, dialect, schema={"t": {"amount": "INT"}}) == candidate


@pytest.mark.parametrize("dialect", [None, "", "not_a_dialect", "fabricspark"])
def test_direct_optimizer_validates_dialect_at_its_boundary(dialect):
    with pytest.raises(SpecError):
        optimize_source("select 1 as n", dialect)
