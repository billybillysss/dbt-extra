"""Template mechanisms accept explicit contexts without project adapters."""

import pytest

from dbt_extra.sql.models import UnsupportedSQL
from dbt_extra.sql.templates.expansion import expand_static
from dbt_extra.sql.templates.macros import classify_calls, macro_definitions


def test_explicit_macro_context_isolated_between_calls():
    definitions = macro_definitions([
        ("demo", "{% macro amount() %}1 + 2{% endmacro %}", "amount.sql"),
    ])
    calls = classify_calls("select {{ amount() }} as total", "duckdb",
                           definitions=definitions, package="demo")
    assert len(calls) == 1 and calls[0].sql == "1 + 2" and calls[0].single_column
    assert expand_static("{% if true %}select {{ amount() }} as total{% endif %}",
                         definitions=definitions, package="demo") == "select 1 + 2 as total"
    unresolved = classify_calls("select {{ amount() }} as total", "duckdb")
    assert unresolved[0].sql is None and "no local static definition" in unresolved[0].reason
    with pytest.raises(UnsupportedSQL, match="no local static definition"):
        expand_static("{% if true %}select {{ amount() }} as total{% endif %}")


def test_static_expansion_preserves_literal_relation_calls():
    code = "{% if true %}select id from {{ ref('orders') }}{% endif %}"
    assert expand_static(code) == "select id from {{ ref('orders') }}"
