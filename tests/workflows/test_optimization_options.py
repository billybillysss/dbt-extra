"""Explicit macro expansion writeback and the single no-write CLI option."""

import pytest

from dbt_extra.config import validate_settings
from dbt_extra.errors import SpecError
from dbt_extra.files.yaml import load_yaml
from dbt_extra.optimization import optimize
from dbt_extra.sql.macros import macro_calls, parse_model
from tests.helpers import invoke, project, put, snapshot


@pytest.fixture
def macro_model(native):
    put(native, "macros/value.sql", """{% macro twice(value) %}{{ value }} + {{ value }}{% endmacro %}
{% macro total(value) %}{{ twice(value) }}{% endmacro %}
{% macro columns(names) %}{% for name in names %}{{ name }}{% if not loop.last %}, {% endif %}{% endfor %}{% endmacro %}
{% macro filter_rows() %}WHERE o.amount > 1{% endmacro %}
""")
    path = put(native, "models/expanded.sql", """{{ config(materialized='view', tags=['macro']) }}
-- preserve this explanation
select {{ total('o.amount') }} as total from {{ ref('orders') }} o
""")
    return path


@pytest.mark.parametrize("format", ["pretty", "compact"])
def test_expansion_preview_and_writeback(native, macro_model, format):
    original = snapshot(native)
    p = project(native)
    parsed = parse_model(p, macro_model.read_text(encoding="utf-8"), expand=True)
    arguments = ("optimize", "--select", "expanded", "--expand", "true", "--format", format)
    preview = invoke(native, *arguments, "--preview")
    assert preview.exit_code == 0, preview.output
    assert "1 structurally rewritten" in preview.output
    assert "SQL files written: 0" in preview.output
    assert "o.amount + o.amount" in preview.output
    assert snapshot(native) == original

    applied = invoke(native, *arguments)
    assert applied.exit_code == 0, applied.output
    assert "SQL files written: 1" in applied.output
    candidate = macro_model.read_text(encoding="utf-8")
    assert not macro_calls(candidate)
    assert "{{ ref('orders') }}" in candidate
    assert "preserve this explanation" in candidate
    assert parse_model(p, candidate).config == parsed.config
    assert [v.output_name for v in parse_model(p, candidate).tree.selects] == ["total"]
    changed = snapshot(native)
    assert {path for path in original if original[path] != changed[path]} == {"models/expanded.sql"}
    second = invoke(native, *arguments)
    assert second.exit_code == 0, second.output
    assert "SQL files written: 0" in second.output
    assert snapshot(native) == changed


@pytest.mark.parametrize("code,outputs,boundary", [
    ("select {{ columns(['o.id', 'o.amount']) }} from {{ ref('orders') }} o", ["id", "amount"], "{{ ref('orders') }}"),
    ("select o.id from {{ ref('orders') }} o {{ filter_rows() }}", ["id"], "{{ ref('orders') }}"),
    ("select {{ total('o.amount') }} as total from {{ source('raw', 'orders') }} o", ["total"], "{{ source('raw', 'orders') }}"),
])
def test_expands_multi_column_clause_and_nested_macros(native, macro_model, code, outputs, boundary):
    macro_model.write_text(code, encoding="utf-8")
    p = project(native)
    changes, skipped = optimize(p, select=["expanded"], expand=True)
    assert not skipped
    candidate = changes.after[macro_model].decode()
    assert not macro_calls(candidate)
    assert boundary in candidate
    assert [v.output_name for v in parse_model(p, candidate).tree.selects] == outputs
    assert changes.optimization_report["model.shop.expanded"]["status"] == "rewritten"
    if "filter_rows" in code:
        assert "o.amount > 1" in candidate


@pytest.mark.parametrize("flags", [(), ("--expand", "false")])
def test_default_and_explicit_false_preserve_macros(native, macro_model, flags):
    response = invoke(native, "optimize", "--select", "expanded", *flags)
    assert response.exit_code == 0, response.output
    assert "{{ total('o.amount') }}" in macro_model.read_text(encoding="utf-8")


@pytest.mark.parametrize("flags,expanded", [((), True), (("--expand", "false"), False)])
def test_expansion_config_and_cli_precedence(native, macro_model, flags, expanded):
    put(native, "extra_project.yaml", "version: 2\noptimization:\n  expand: true\n")
    response = invoke(native, "optimize", "--select", "expanded", *flags)
    assert response.exit_code == 0, response.output
    assert bool(macro_calls(macro_model.read_text(encoding="utf-8"))) is not expanded


@pytest.mark.parametrize("definition,call,reason", [
    ("", "{{ missing('o.amount') }}", "no local static definition"),
    ("{% macro bad(v) %}{{ env_var('VALUE') }}{% endmacro %}", "{{ bad('o.amount') }}", "remains opaque"),
    ("{% macro bad(v) %}{{ bad(v) }}{% endmacro %}", "{{ bad('o.amount') }}", "Recursive macro expansion"),
    ("{% macro bad(v) %}random(){% endmacro %}", "{{ bad('o.amount') }}", "Volatile or unknown"),
    ("{% macro bad(v) %}{{ v }}{% endmacro %}", "{{- bad('o.amount') }}", "Whitespace-controlled"),
])
def test_unsafe_expansion_skips_without_partial_write(native, macro_model, definition, call, reason):
    put(native, "macros/bad.sql", definition)
    macro_model.write_text("select {{ total('o.amount') }} as total, " + call +
        " as bad from {{ ref('orders') }} o", encoding="utf-8")
    before = snapshot(native)
    changes, skipped = optimize(project(native), select=["expanded", "revenue"], expand=True)
    assert reason in skipped["model.shop.expanded"]
    assert macro_model not in changes.after
    assert "model.shop.revenue" in changes.optimization_report
    assert snapshot(native) == before
    changes.apply()
    assert macro_model.read_bytes() == before["models/expanded.sql"]


def test_expansion_settings_validation():
    for value in (False, True):
        validate_settings({"optimization": {"expand": value}})
    with pytest.raises(SpecError, match="expected a boolean"):
        validate_settings({"optimization": {"expand": "true"}})


def test_init_configures_expansion_and_preview_writes_nothing(native):
    before = snapshot(native)
    preview = invoke(native, "init", "--preview")
    assert preview.exit_code == 0, preview.output
    assert snapshot(native) == before
    applied = invoke(native, "init")
    assert applied.exit_code == 0, applied.output
    settings = load_yaml(native / "extra_project.yaml")
    assert settings["optimization"] == {"format": "pretty", "expand": False}
