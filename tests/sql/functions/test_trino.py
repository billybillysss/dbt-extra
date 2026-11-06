"""Trino recognition, inference and conservative rewrite contracts."""

import pytest

from dbt_extra.sql.functions import TRINO
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", TRINO, ids=lambda f: f.name)
def test_trino_recognition_and_shape(spec):
    recognition("trino", spec)


@pytest.mark.parametrize("spec", TRINO, ids=lambda f: f.name)
def test_trino_return_types(spec):
    typing("trino", spec)


@pytest.mark.parametrize("spec", TRINO, ids=lambda f: f.name)
def test_trino_rewrite_safety(spec):
    safety("trino", spec)


@pytest.mark.parametrize("spec", TRINO, ids=lambda f: f.name)
def test_trino_metadata_enrichment(native, spec):
    enrichment(native, "trino", spec)


def test_trino_documented_catalog():
    documentation("trino", TRINO)
