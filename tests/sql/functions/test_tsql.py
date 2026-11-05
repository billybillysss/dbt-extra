"""T-SQL: scalar, aggregate and table-valued gaps have separate contracts."""

import pytest

from dbt_extra.sql.functions import TSQL
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", TSQL, ids=lambda f: f.name)
def test_tsql_recognition_and_shape(spec):
    recognition("tsql", spec)


@pytest.mark.parametrize("spec", TSQL, ids=lambda f: f.name)
def test_tsql_return_types(spec):
    typing("tsql", spec)


@pytest.mark.parametrize("spec", TSQL, ids=lambda f: f.name)
def test_tsql_rewrite_safety(spec):
    safety("tsql", spec)


@pytest.mark.parametrize("spec", TSQL, ids=lambda f: f.name)
def test_tsql_metadata_enrichment(native, spec):
    enrichment(native, "tsql", spec)


def test_tsql_documented_catalog():
    documentation("tsql", TSQL)
