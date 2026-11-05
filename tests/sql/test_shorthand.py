"""Review shorthand must never change literals, comments or complex templates."""

import pytest

from dbt_extra.errors import SpecError
from dbt_extra.sql.shorthand import display, restore, output_spans


@pytest.mark.parametrize("raw,short", [
    ("{{ ref('orders') }}", "ref.orders"),
    ('{{ref("pkg", "orders")}}', "ref.pkg.orders"),
    ("{{ source('raw', 'orders') }}", "source.raw.orders"),
    ("{{ round_money('amount') }}", "macro.round_money('amount')"),
    ("{{ shop.round_money('amount', precision=2) }}", "macro.shop.round_money('amount', precision=2)"),
    ("{{ columns(['id', 'amount']) }}", "macro.columns(['id', 'amount'])"),
    ("{{ ref(['orders']) }}", "{{ ref(['orders']) }}"),
])
def test_simple_calls_roundtrip_verbatim_inside_edited_sql(raw, short):
    original = "FROM " + raw
    assert display(original) == "FROM " + short
    assert restore("FROM " + short + " WHERE id > 1", original) == original + " WHERE id > 1"


@pytest.mark.parametrize("raw", [
    "{{ ref('orders', version=2) }}", "{{ ref(var('name')) }}",
    "{{ ref('name-with-dash') }}", "{{ config(materialized='view') }}",
    "{{- ref('orders') -}}", "{{ round_money(var('field')) }}", "{{ value | upper }}",
    "{{ macro_name('}}') }}",
])
def test_complex_calls_keep_valid_original_syntax(raw):
    short = display(raw)
    assert restore(short, raw) == raw
    if "macro_name" not in raw:
        assert short == raw


@pytest.mark.parametrize("protected", [
    "'ref.orders macro.round_money(1)'", '"ref.orders"', '`source.raw.orders`',
    "[ref.orders]", "-- ref.orders\n", "/* source.raw.orders */", "$$ref.orders$$",
    "$sql$macro.round_money(1)$sql$", "{# ref.orders #}", "{% raw %}ref.orders{% endraw %}",
    "'{{ ref(\"orders\") }}'", "-- {{ ref('orders') }}\n",
    "/* outer /* inner */ ref.orders {{ ref('orders') }} */",
])
def test_literals_comments_and_raw_blocks_are_not_rewritten(protected):
    assert display(protected) == protected
    assert restore(protected) == protected


def test_existing_sql_qualifiers_are_not_mistaken_for_new_shorthand():
    original = "ref.amount + source.raw.amount + macro.udf(1)"
    assert restore(original + " + 1", original) == original + " + 1"


def test_new_shorthand_restores_templates():
    assert restore("FROM ref.orders JOIN source.raw.orders o ON true") == "FROM {{ ref('orders') }} JOIN {{ source('raw', 'orders') }} o ON true"
    assert restore("macro.shop.round_money('net', precision=3)") == "{{ shop.round_money('net', precision=3) }}"
    with pytest.raises(SpecError, match="Unclosed"):
        restore("macro.round_money('amount'")


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_template_offsets_preserve_original_newlines(newline):
    code = newline.join(["-- header", "select {{ round_money('amount') }} as amount", "-- footer"])
    start, end, raw, _ = next(output_spans(code))
    assert code[start:end] == raw == "{{ round_money('amount') }}"
