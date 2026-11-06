"""Redshift gap contracts, independent of native PostgreSQL functions."""

import pytest

from dbt_extra.sql.functions import REDSHIFT
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", REDSHIFT, ids=lambda f: f.name)
def test_redshift_recognition_and_shape(spec):
    recognition("redshift", spec)


@pytest.mark.parametrize("spec", REDSHIFT, ids=lambda f: f.name)
def test_redshift_return_types(spec):
    typing("redshift", spec)


@pytest.mark.parametrize("spec", REDSHIFT, ids=lambda f: f.name)
def test_redshift_rewrite_safety(spec):
    safety("redshift", spec)


@pytest.mark.parametrize("spec", REDSHIFT, ids=lambda f: f.name)
def test_redshift_metadata_enrichment(native, spec):
    enrichment(native, "redshift", spec)


def test_redshift_documented_catalog():
    documentation("redshift", REDSHIFT)
