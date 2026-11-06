"""BigQuery dependent scalar types must not be guessed or made generators."""

import pytest

from dbt_extra.sql.functions import BIGQUERY
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", BIGQUERY, ids=lambda f: f.name)
def test_bigquery_recognition_and_shape(spec):
    recognition("bigquery", spec)


@pytest.mark.parametrize("spec", BIGQUERY, ids=lambda f: f.name)
def test_bigquery_return_types(spec):
    typing("bigquery", spec)


@pytest.mark.parametrize("spec", BIGQUERY, ids=lambda f: f.name)
def test_bigquery_rewrite_safety(spec):
    safety("bigquery", spec)


@pytest.mark.parametrize("spec", BIGQUERY, ids=lambda f: f.name)
def test_bigquery_metadata_enrichment(native, spec):
    enrichment(native, "bigquery", spec)


def test_bigquery_documented_catalog():
    documentation("bigquery", BIGQUERY)
