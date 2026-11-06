"""PostgreSQL: fixed types do not authorize evaluation or session changes."""

import pytest

from dbt_extra.sql.functions import POSTGRES
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", POSTGRES, ids=lambda f: f.name)
def test_postgres_recognition_and_shape(spec):
    recognition("postgres", spec)


@pytest.mark.parametrize("spec", POSTGRES, ids=lambda f: f.name)
def test_postgres_return_types(spec):
    typing("postgres", spec)


@pytest.mark.parametrize("spec", POSTGRES, ids=lambda f: f.name)
def test_postgres_rewrite_safety(spec):
    safety("postgres", spec)


@pytest.mark.parametrize("spec", POSTGRES, ids=lambda f: f.name)
def test_postgres_metadata_enrichment(native, spec):
    enrichment(native, "postgres", spec)


def test_postgres_documented_catalog():
    documentation("postgres", POSTGRES)
