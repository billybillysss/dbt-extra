import pytest

from dbt_extra.errors import SpecError
from dbt_extra.inspection import inspect
from dbt_extra.optimization import optimize
from dbt_extra.sql.rewrites.engine import optimize_source
from dbt_extra.project.model_sql import parse_model
from dbt_extra.sql.parser import parse_authored
from dbt_extra.sql.renderer import render
from tests.helpers import project, put


STATIC = """{# static threshold; no runtime context #}
{% set threshold = 2 %}
SELECT id, {% for metric in ['a', 'b', 'c'] %}
SUM({{ metric }}) AS {{ metric }}_sum{% if not loop.last %},{% endif %}
{% endfor %}
FROM {{ ref('orders') }} WHERE id > {{ threshold }} GROUP BY id
"""


def test_literal_top_level_analysis_and_authored_preservation(native):
    path = put(native, "models/static.sql", STATIC)
    p = project(native)
    parsed = parse_model(p, STATIC, expand=True)
    assert [c.output_name for c in parsed.tree.selects] == ["id", "a_sum", "b_sum", "c_sum"]
    assert "2" in parsed.tree.sql() and len(parsed.refs) == 1
    assert optimize_source(STATIC, "duckdb") == STATIC
    assert render(parse_authored(STATIC, "duckdb").tree, parse_authored(STATIC, "duckdb"), "duckdb") == STATIC
    changes, skipped = optimize(p, select=["static"])
    assert not skipped and changes.after[path] == path.read_bytes()
    changes, skipped = optimize(p, select=["static"], expand=True)
    assert not skipped
    assert "{%" not in changes.after[path].decode() and "{{ ref('orders') }}" in changes.after[path].decode()
    tree, _, _ = inspect(p, "static", compiled=False)
    assert [c.output_name for c in tree.selects] == ["id", "a_sum", "b_sum", "c_sum"]


@pytest.mark.parametrize("code,names", [
    ("{% set n = 2 %} SELECT {{ n }} AS k", ["k"]),
    ("{%- set n = 2 -%}\n SELECT {{ n }} AS k", ["k"]),
    ("{% for a in ['x','y'] %}{% for b in ['1','2'] %}{% if loop.first %}SELECT {% endif %} 1 AS {{a}}{{b}}{% if not loop.last %}, {% endif %}{% endfor %}{% if not loop.last %} UNION ALL {% endif %}{% endfor %}", ["x1", "x2"]),
    ("{% if false %} {{ var('never_evaluated') }} {% else %} SELECT 1 AS k {% endif %}", ["k"]),
    ("{% set b = true %}{% if b %}SELECT 1 AS k{% else %}invalid{% endif %}", ["k"]),
    ("{% if false %}invalid{% elif 2 > 1 %}SELECT 1 AS k{% else %}invalid{% endif %}", ["k"]),
    ("{# {{ var('ignored') }} #}\r\n{% set n=2 %}\r\n SELECT {{ n }} AS k", ["k"]),
    ("{% set n=2 %} {{- config(materialized='view') -}} SELECT {{ n }} AS k FROM {{ ref('orders') }}", ["k"]),
])
def test_comments_whitespace_nested_scopes_and_literal_dbt_calls(code, names):
    parsed = parse_authored(code, "duckdb")
    assert [p.output_name for p in parsed.tree.selects] == names


@pytest.mark.parametrize("code", [
    "{% if is_incremental() %} SELECT 1 AS k {% else %} SELECT 2 AS k {% endif %}",
    "{% set n = var('threshold') %} SELECT {{ n }} AS k",
    "{% set n = env_var('SECRET') %} SELECT {{ n }} AS k",
    "{% set n = run_query('select 1') %} SELECT {{ n }} AS k",
    "{% for x in range(1001) %}{{ x }}{% endfor %}",
    "{% for x in ['a'] recursive %}SELECT 1{% endfor %}",
    "{% set n = namespace(x=1) %} SELECT 1 AS k",
    "{% set n = 'SELECT 1; DELETE FROM t' %} {{ n }}",
    "{% set n = '{{ var(\"x\") }}' %} SELECT {{ n }} AS k",
    "{% set n = 'x' %} SELECT {{ ref(n) }}",
])
def test_runtime_and_unsupported_shapes_are_not_invented(code):
    with pytest.raises(SpecError):
        parse_authored(code, "duckdb")


def test_size_iteration_work_depth_and_token_collision_limits():
    codes = [
        "{% for x in [" + ",".join("1" for _ in range(1001)) + "] %} SELECT 1 {% endfor %}",
        "{% for x in [1,2] %}" * 14 + "x" + "{% endfor %}" * 14,
        "{% set x = '" + "x" * 100001 + "' %} SELECT '{{ x }}' AS k",
        "{% if true %}" * 22 + "SELECT 1 AS k" + "{% endif %}" * 22,
    ]
    for code in codes:
        with pytest.raises(SpecError):
            parse_authored(code, "duckdb")
    import hashlib
    raw = "{{ ref('orders') }}"
    token = "extra_static_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    with pytest.raises(SpecError, match="collision"):
        parse_authored("{% set n=1 %} SELECT '" + token + "' FROM " + raw, "duckdb")
