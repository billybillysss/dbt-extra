"""Spark: only actual SQLGlot gaps, not a list of native built-ins."""

import pytest

from dbt_extra.sql.functions import SPARK
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", SPARK, ids=lambda f: f.name)
def test_spark_recognition_and_shape(spec):
    recognition("spark", spec)


@pytest.mark.parametrize("spec", SPARK, ids=lambda f: f.name)
def test_spark_return_types(spec):
    typing("spark", spec)


@pytest.mark.parametrize("spec", SPARK, ids=lambda f: f.name)
def test_spark_rewrite_safety(spec):
    safety("spark", spec)


@pytest.mark.parametrize("spec", SPARK, ids=lambda f: f.name)
def test_spark_metadata_enrichment(native, spec):
    enrichment(native, "spark", spec)


def test_spark_documented_catalog():
    documentation("spark", SPARK)
