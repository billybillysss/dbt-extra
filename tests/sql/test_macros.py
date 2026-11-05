"""Static macro previews: scalar calls stay reversible; expansion can emit many columns."""

import pytest

from dbt_extra.errors import SpecError
from dbt_extra.inspection import inspect
from dbt_extra.sql.macros import parse_model, classify_calls, contains_opaque
from dbt_extra.sql.renderer import render
from tests.helpers import project, put


SCALAR = "{% macro round_money(value, precision=2) %}round({{ value }}, {{ precision }}){% endmacro %}"


@pytest.mark.parametrize("dialect", ["duckdb", "postgres", "snowflake", "bigquery", "spark", "tsql"])
def test_scalar_preview_restores_call_and_expansion_inlines_sql(native, dialect):
    put(native, "macros/money.sql", SCALAR)
    code = "select {{ round_money('amount', precision=3) }} as total from {{ ref('orders') }}"
    p = project(native)
    p.dialect = dialect
    parsed = parse_model(p, code)
    assert "{{ round_money('amount', precision=3) }}" in render(parsed.tree, parsed, dialect)
    assert "extra_macro_" not in render(parsed.tree, parsed, dialect)
    expanded = parse_model(p, code, expand=True)
    assert "ROUND(AMOUNT, 3)" in render(expanded.tree, expanded, dialect).upper()
    assert "round_money" not in render(expanded.tree, expanded, dialect)


def test_multi_column_loop_expands_to_actual_projections(native):
    put(native, "macros/columns.sql", "{% macro columns(fields) %}{% for field in fields %}{{ field }}{% if not loop.last %}, {% endif %}{% endfor %}{% endmacro %}")
    code = "select {{ columns(['id', 'amount']) }} from {{ ref('orders') }}"
    p = project(native)
    with pytest.raises(SpecError, match="multiple columns"):
        parse_model(p, code)
    parsed = parse_model(p, code, expand=True)
    assert [col.output_name for col in parsed.tree.selects] == ["id", "amount"]


@pytest.mark.parametrize("body", [
    "{{ adapter.get_columns_in_relation('x') }}", "{{ run_query('delete from x') }}",
    "{{ env_var('SECRET') }}", "{{ var('field') }}", "{{ missing }}",
    "{{ value.__class__ }}", "{% if execute %}1{% else %}2{% endif %}",
    "{{ recursive(value) }}", "{{ value | attr('__class__') }}",
])
def test_context_dependent_or_unsafe_macros_remain_opaque(native, body):
    put(native, "macros/unsafe.sql", "{% macro recursive(value) %}" + body + "{% endmacro %}")
    with pytest.raises(SpecError):
        parse_model(project(native), "select {{ recursive('amount') }} as result", expand=True)


def test_nested_calls_package_defaults_and_if_assignments(native):
    put(native, "macros/money.sql", SCALAR + "{% macro outer(value, rounded=true) %}{% set result = value %}{% if rounded %}{% set result = shop.round_money(value) %}{% endif %}{{ result }}{% endmacro %}")
    p = project(native)
    parsed = parse_model(p, "select {{ shop.outer('amount') }} as total", expand=True)
    assert "ROUND(amount, 2)" in render(parsed.tree, parsed, "duckdb")


def test_inspect_expand_includes_macro_columns_and_keeps_files_unchanged(native):
    put(native, "macros/columns.sql", "{% macro fields() %}id, amount * 2 as doubled{% endmacro %}")
    path = put(native, "models/target.sql", "select {{ fields() }} from {{ ref('orders') }}")
    original = path.read_bytes()
    tree, parsed, _ = inspect(project(native), "target", ["doubled"], expanded=True, optimized=False, compiled=False)
    assert "amount * 2" in render(tree, parsed, "duckdb")
    assert "{{ source('raw', 'orders') }}" in render(tree, parsed, "duckdb")
    assert path.read_bytes() == original
    with pytest.raises(SpecError, match="multiple columns"):
        inspect(project(native), "target", expanded=False)


@pytest.mark.parametrize("expand", [False, True])
def test_whitespace_controlled_calls_remain_opaque(native, expand):
    put(native, "macros/money.sql", SCALAR)
    with pytest.raises(SpecError, match="Whitespace-controlled"):
        parse_model(project(native), "select {{- round_money('amount') -}} as total", expand=expand)


def test_generated_jinja_is_not_interpreted_a_second_time(native):
    put(native, "macros/literal.sql", "{% macro literal() %}{{ \"{{ ref('orders') }}\" }}{% endmacro %}")
    with pytest.raises(SpecError, match="unevaluated Jinja"):
        parse_model(project(native), "select * from {{ literal() }}", expand=True)


@pytest.mark.parametrize("definition", [
    "{% if execute %}{% macro hidden() %}1{% endmacro %}{% endif %}",
    "{% macro outer() %}{% macro hidden() %}1{% endmacro %}{% endmacro %}",
])
def test_nested_or_conditionally_defined_macros_are_not_assumed_available(native, definition):
    put(native, "macros/hidden.sql", definition)
    with pytest.raises(SpecError, match="no local static definition"):
        parse_model(project(native), "select {{ hidden() }} as value", expand=True)


@pytest.mark.parametrize("body", [
    "{% for value in values %}{{ value }}{% endfor %}",
    "{{ 'x' ~ 'y' }}",
])
def test_macro_expansion_limits_fail_explicitly(native, monkeypatch, body):
    from dbt_extra.sql import macros

    put(native, "macros/limited.sql", "{% macro limited(values) %}" + body + "{% endmacro %}")
    monkeypatch.setattr(macros, "LIMIT", 1)
    with pytest.raises(SpecError, match="size limit"):
        parse_model(project(native), "select {{ limited(['x', 'y']) }} as value", expand=True)


def test_literal_tuples_keep_their_jinja_output_representation(native):
    from dbt_extra.sql.macros import StaticMacros
    from dbt_extra.sql.shorthand import output_spans

    put(native, "macros/echo.sql", "{% macro echo(value) %}{{ value }}{% endmacro %}")
    call = next(output_spans("{{ echo((1, 2)) }}"))[3]
    assert StaticMacros(project(native)).call(call) == "(1, 2)"


@pytest.mark.parametrize("expanded", [False, True])
def test_macro_emitting_case_expression_keeps_scalar_shape(native, expanded):
    put(native, "macros/positive.sql", "{% macro positive(value) %}case when {{ value }} > 0 then {{ value }} else 0 end{% endmacro %}")
    parsed = parse_model(project(native), "select {{ positive('amount') }} as total from {{ ref('orders') }}", expand=expanded)
    assert [col.output_name for col in parsed.tree.selects] == ["total"]
    rendered = render(parsed.tree, parsed, "duckdb")
    if expanded:
        assert "CASE" in rendered and "WHEN amount > 0" in rendered and "ELSE 0" in rendered
        assert "positive(" not in rendered
    else:
        assert "{{ positive('amount') }}" in rendered
    assert "{{ ref('orders') }}" in rendered and "extra_macro_" not in rendered


@pytest.mark.parametrize("body", ["sum({{ value }})", "row_number() over (partition by {{ value }} order by id)",
                                  "{{ value }} as total"])
def test_aggregate_window_and_aliased_macros_have_one_output(native, body):
    put(native, "macros/value.sql", "{% macro value(value) %}" + body + "{% endmacro %}")
    call = "{{ value('amount') }}"
    code = "select " + call + ("" if "as total" in body else " as total") + " from {{ ref('orders') }}"
    p = project(native)
    assert classify_calls(p, code)[0].single_column
    parsed = parse_model(p, code)
    assert [c.output_name for c in parsed.tree.selects] == ["total"]
    rendered = render(parsed.tree, parsed, "duckdb")
    assert call in rendered and "extra_macro_" not in rendered
    assert rendered.lower().count("as total") == (0 if "as total" in body else 1)


def test_partial_macro_parsing_keeps_independent_call_boundaries(native):
    put(native, "macros/money.sql", SCALAR)
    code = "select {{ unknown() }}, {{ round_money('amount') }} as total from {{ ref('orders') }}"
    p = project(native)
    calls = classify_calls(p, code)
    assert calls[0].sql is None and "no local static definition" in calls[0].reason
    assert calls[1].single_column and calls[1].sql == "round(amount, 2)"
    with pytest.raises(SpecError, match="no local static definition"):
        parse_model(p, code)
    parsed = parse_model(p, code, partial=True)
    assert contains_opaque(parsed.tree.selects[0], parsed)
    assert not contains_opaque(parsed.tree.selects[1], parsed)
    assert "{{ unknown() }}" in render(parsed.tree, parsed, "duckdb")
