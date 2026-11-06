"""Fabric Warehouse: independently verified gaps, not inherited T-SQL coverage."""

import pytest

from dbt_extra.sql.functions import FABRIC
from tests.sql.functions.helpers import documentation, enrichment, recognition, safety, typing


@pytest.mark.parametrize("spec", FABRIC, ids=lambda f: f.name)
def test_fabric_recognition_and_shape(spec):
    recognition("fabric", spec)


@pytest.mark.parametrize("spec", FABRIC, ids=lambda f: f.name)
def test_fabric_return_types(spec):
    typing("fabric", spec)


@pytest.mark.parametrize("spec", FABRIC, ids=lambda f: f.name)
def test_fabric_rewrite_safety(spec):
    safety("fabric", spec)


@pytest.mark.parametrize("spec", FABRIC, ids=lambda f: f.name)
def test_fabric_metadata_enrichment(native, spec):
    enrichment(native, "fabric", spec)


def test_fabric_documented_catalog():
    documentation("fabric", FABRIC)
