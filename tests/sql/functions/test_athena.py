"""Athena engine-3 evidence does not imply Trino catalog inheritance."""

import pytest

from dbt_extra.sql.functions import ATHENA
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", ATHENA, ids=lambda f: f.name)
def test_athena_recognition_and_shape(spec):
    recognition("athena", spec)


@pytest.mark.parametrize("spec", ATHENA, ids=lambda f: f.name)
def test_athena_return_types(spec):
    typing("athena", spec)


@pytest.mark.parametrize("spec", ATHENA, ids=lambda f: f.name)
def test_athena_rewrite_safety(spec):
    safety("athena", spec)


@pytest.mark.parametrize("spec", ATHENA, ids=lambda f: f.name)
def test_athena_metadata_enrichment(native, spec):
    enrichment(native, "athena", spec)


def test_athena_documented_catalog():
    documentation("athena", ATHENA)
