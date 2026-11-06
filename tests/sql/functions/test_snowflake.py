"""Snowflake context functions remain opaque despite fixed return families."""

import pytest

from dbt_extra.sql.functions import SNOWFLAKE
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", SNOWFLAKE, ids=lambda f: f.name)
def test_snowflake_recognition_and_shape(spec):
    recognition("snowflake", spec)


@pytest.mark.parametrize("spec", SNOWFLAKE, ids=lambda f: f.name)
def test_snowflake_return_types(spec):
    typing("snowflake", spec)


@pytest.mark.parametrize("spec", SNOWFLAKE, ids=lambda f: f.name)
def test_snowflake_rewrite_safety(spec):
    safety("snowflake", spec)


@pytest.mark.parametrize("spec", SNOWFLAKE, ids=lambda f: f.name)
def test_snowflake_metadata_enrichment(native, spec):
    enrichment(native, "snowflake", spec)


def test_snowflake_documented_catalog():
    documentation("snowflake", SNOWFLAKE)
