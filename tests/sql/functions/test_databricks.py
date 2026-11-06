"""Databricks: independently verified gaps, not inherited Spark coverage."""

import pytest

from dbt_extra.sql.functions import DATABRICKS
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", DATABRICKS, ids=lambda f: f.name)
def test_databricks_recognition_and_shape(spec):
    recognition("databricks", spec)


@pytest.mark.parametrize("spec", DATABRICKS, ids=lambda f: f.name)
def test_databricks_return_types(spec):
    typing("databricks", spec)


@pytest.mark.parametrize("spec", DATABRICKS, ids=lambda f: f.name)
def test_databricks_rewrite_safety(spec):
    safety("databricks", spec)


@pytest.mark.parametrize("spec", DATABRICKS, ids=lambda f: f.name)
def test_databricks_metadata_enrichment(native, spec):
    enrichment(native, "databricks", spec)


def test_databricks_documented_catalog():
    documentation("databricks", DATABRICKS)
