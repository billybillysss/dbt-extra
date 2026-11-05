"""Authored macro boundaries for reversible per-macro review edits."""

import pytest

from dbt_extra.sql.jinja import macro_blocks


@pytest.mark.parametrize("prefix,suffix", [
    ("-- Header\n", "\n-- Footer\n"),
    ("{# {% macro fake() %}x{% endmacro %} #}\n", ""),
    ("{% raw %}{% macro fake() %}x{% endmacro %}{% endraw %}\n", ""),
    ("{{ '{% macro fake() %}' }}\n", ""),
])
@pytest.mark.parametrize("macro", [
    "{% macro actual(value) %}{{ value }}{% endmacro %}",
    "{%- macro actual(value) -%}\n {{ value }}\n{%- endmacro -%}",
    "{% macro actual(value) %}{{ '{% endmacro %}' }}{% endmacro %}",
])
def test_macro_spans_ignore_template_literals_and_preserve_offsets(prefix, suffix, macro):
    code = prefix + macro + suffix
    blocks = macro_blocks(code)
    assert blocks == [{"name": "actual", "start": len(prefix), "end": len(prefix) + len(macro)}]
    assert code[blocks[0]["start"]:blocks[0]["end"]] == macro
