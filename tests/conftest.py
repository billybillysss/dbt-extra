"""Shared fixtures for dbt companion tests."""

import pytest

from tests.helpers import native


@pytest.fixture(autouse=True)
def no_project_environment(monkeypatch):
    monkeypatch.delenv("EXTRA_PROJECT_DIR", raising=False)
    monkeypatch.delenv("DBT_PROJECT_DIR", raising=False)
