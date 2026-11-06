"""Check supported interpretation against actual Jinja, not itself."""

import duckdb
from jinja2 import UndefinedError
import pytest

from dbt_extra.errors import SpecError
from dbt_extra.optimization import optimize
from dbt_extra.project.model_sql import parse_model
from dbt_extra.sql.renderer import render
from tests.helpers import project, put
from tests.semantics import assert_equivalent, render_jinja


DEFINITIONS = """
{% macro twice(value) %}{{ value }} + {{ value }}{% endmacro %}
{% macro money(value, precision=2) %}ROUND({{ value }}, {{ precision }}){% endmacro %}
{% macro fields(values) %}{% for name, expr in values %}{{ expr }} AS {{ name }}{% if not loop.last %},{% endif %}{% endfor %}{% endmacro %}
{% macro choose(value, enabled=true) %}{% set result=value %}{% if enabled %}{% set result=twice(value) %}{% endif %}{{ result }}{% endmacro %}
{% macro text(value) %}'{{ value.strip() | upper | trim }}'{% endmacro %}
"""
QUERIES = [
    "SELECT id, {{ twice('amount') }} AS total FROM orders ORDER BY total NULLS LAST,id",
    "SELECT id, {{ shop.money('amount', precision=3) }} AS total FROM orders",
    "SELECT {{ fields([('key','id'),('total','amount')]) }} FROM orders ORDER BY key,total",
    "SELECT {{ choose('amount') }} AS total FROM orders",
    "SELECT {{ choose('amount', enabled=false) }} AS total FROM orders",
    "SELECT {{ text(' aBc ') }} AS value FROM orders",
    "{% set threshold=2 %}SELECT id FROM orders WHERE amount>{{ threshold }} ORDER BY id",
    "{% set threshold=2 %}SELECT id, {% for name in ['amount','id'] %}{{ name }} AS x{{ loop.index }}{% if not loop.last %},{% endif %}{% endfor %} FROM orders ORDER BY id,x1",
    "{% set flag=true %}{% if false %}invalid{% elif flag and 2 > 1 %}SELECT id FROM orders{% else %}invalid{% endif %}",
    "{%- set value=' aBc ' -%} SELECT '{{ value.strip() | lower }}' AS value FROM orders",
    "{% set label='outer' %}{% for label in ['inner'] %}{% set label='changed' %}{% endfor %}SELECT '{{ label }}' AS value FROM orders",
]


@pytest.mark.parametrize("code", QUERIES)
@pytest.mark.parametrize("expand", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_interpreter_and_optimizer_match_real_jinja(native, code, expand, empty):
    put(native, "macros/oracle.sql", DEFINITIONS)
    path = put(native, "models/oracle.sql", code)
    p = project(native)
    expected = render_jinja(native, code)
    interpreted = parse_model(p, code, expand=True)
    interpreted_sql = render_jinja(native, render(interpreted.tree, interpreted, "duckdb"))
    changes, skipped = optimize(p, select=["oracle"], expand=expand)
    if "{{ fields(" in code and not expand:
        assert "model.shop.oracle" in skipped and path not in changes.after
        candidate = expected
    else:
        assert not skipped
        candidate = render_jinja(native, changes.after[path].decode())
    with duckdb.connect() as con:
        con.execute("CREATE TABLE orders(id INT,amount DECIMAL(12,2))")
        if not empty:
            con.execute("INSERT INTO orders VALUES (1,2.25),(1,2.25),(2,2.25),(NULL,NULL),(3,-1.01)")
        assert_equivalent(con, expected, interpreted_sql)
        assert_equivalent(con, expected, candidate)


def test_nonexistent_trim_method_is_not_invented(native):
    put(native, "macros/bad.sql", "{% macro bad(value) %}'{{ value.trim() }}'{% endmacro %}")
    code = "SELECT {{ bad(' x ') }} AS value"
    with pytest.raises(UndefinedError):
        render_jinja(native, code)
    with pytest.raises(SpecError):
        parse_model(project(native), code, expand=True)
