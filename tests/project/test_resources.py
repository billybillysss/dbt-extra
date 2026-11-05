"""Resource provenance, identity, and selector behavior."""

import pytest

from dbt_extra import Project, SpecError
from dbt_extra.project.resources import Resource
from dbt_extra.project.selectors import select
from tests.helpers import put


def resource(**kwargs):
    return Resource("model.shop.orders", "orders", "model", "shop", None, "models/slv/orders.sql", "slv", **kwargs)


def test_stale_artifacts_do_not_override_authored_evidence():
    model = resource(properties={"columns": [{"name": "id", "description": "Authored"}], "config": {"materialized": "table"}},
                     node={"columns": {"id": {"data_type": "BIGINT"}}, "config": {"tags": ["stale"]}},
                     inherited_config={"tags": ["inherited"]}, inline_config={"materialized": "view"},
                     catalog_columns={"id": {"data_type": "INTEGER"}})
    assert model.known_columns["id"] == {"name": "id", "description": "Authored", "data_type": "BIGINT"}
    assert model.config == {"tags": ["stale"], "materialized": "view"}
    model.stale = True
    assert model.known_columns == {"id": {"name": "id", "description": "Authored"}}
    assert model.config == {"tags": ["inherited"], "materialized": "view"}


def test_selectors_use_authored_paths_not_directory_only_model_paths():
    model = resource(inline_config={"tags": ["finance"]})
    assert select([model], ["path:models/slv/**"]) == [model]
    assert select([model], ["tag:finance"], exclude=["package:other"]) == [model]
    assert select([model], exclude=[model.id]) == []
    with pytest.raises(SpecError, match="Unsupported selector"):
        select([model], ["layer:slv"])


def test_legacy_semantic_settings_are_not_a_second_input_mode(tmp_path):
    put(tmp_path, "dbt_project.yml", "name: shop\n")
    put(tmp_path, "extra_project.yaml", "version: 1\nmodels: models\n")
    with pytest.raises(SpecError):
        Project(tmp_path, dialect="duckdb")
