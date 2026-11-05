"""Config-only pretty printing preserves Jinja expressions and authored tokens."""

import pytest

from dbt_extra.optimization import optimize_source
from dbt_extra.sql.config_format import format_configs
from dbt_extra.sql.jinja import validate_template
from tests.helpers import invoke, put, snapshot


COMPACT = "{{ config(materialized='view', meta={'domain': 'sales'}) }}"
PRETTY = """{{ config(
    materialized='view',
    meta={
        'domain': 'sales'
    }
) }}"""


def test_pretty_config_dictionary():
    assert format_configs(COMPACT) == PRETTY
    assert format_configs(PRETTY) == PRETTY
    assert format_configs(PRETTY, pretty=False) == COMPACT


@pytest.mark.parametrize("pretty", [True, False])
@pytest.mark.parametrize("raw", [
    COMPACT,
    '{{config(materialized="view", tags=["sales", "daily"], meta={"owner": {"name": "O\'Brien"}})}}',
    "{{ config({'materialized':'view', 'meta':{'domain':'sales'}}, tags=[]) }}",
    "{{ config(meta={}, tags=[], enabled=true, persist_docs={'relation': false}, alias=none) }}",
    "{{ config(materialized=var('storage'), meta={'owner': env_var('OWNER', 'a,b:c')}) }}",
    "{{ config(meta={'x': [1, {'y': [2, 3]}]}, tags=['a', 'b'],) }}",
    "{{ config(meta={'a': 1, 'a': 2}, alias=('a',), tags=(['a'] + ['b'])) }}",
    "{{ config(tags=['x'] + ['y'], meta={'x': 1} | combine(var('meta'))) }}",
    "{{ config(alias='brackets [ ] { } ( ),:= and \\'quotes\\'', meta={'x': '\\n'}) }}",
    "{{ config(enabled=target.name == 'prod', tags=var('tags', ['a', 'b'])) }}",
    "{{ config(*args, **kwargs) }}",
    "{{ config() }}",
    "{{ config(meta={'text': '}} and {{ and , : ='}) }}",
    "{{ config(meta={'text': 'first\nsecond'}) }}",
])
def test_structure_quotes_order_dynamic_expressions_and_fixed_point(raw, pretty):
    candidate = format_configs(raw, pretty=pretty)
    assert validate_template(candidate) == validate_template(raw)
    assert format_configs(candidate, pretty=pretty) == candidate
    assert format_configs(candidate, pretty=False).count("\n") == raw.count("\n")


def test_nested_indentation():
    assert format_configs("{{ config(meta={'owners': ['sales', {'name': 'a'}]}) }}") == """{{ config(
    meta={
        'owners': [
            'sales',
            {
                'name': 'a'
            }
        ]
    }
) }}"""


def test_compact_nested_containers_and_multiline_expressions():
    raw = """{{ config(
    materialized=var(
        'storage', 'view'
    ),
    meta={'owners': ['sales', {'name': 'a'}]},
    tags=[],
) }}"""
    candidate = format_configs(raw)
    assert "materialized=var(\n        'storage', 'view'\n    )" in candidate
    assert format_configs(candidate, pretty=False) == (
        "{{ config(materialized=var( 'storage', 'view' ), "
        "meta={'owners': ['sales', {'name': 'a'}]}, tags=[]) }}"
    )


def test_literal_crlf_and_quote_spelling_are_preserved():
    raw = '{{ config(meta={"text": "first\r\nsecond", \'escaped\': \'a\\\'b\'}) }}'
    for pretty in (True, False):
        candidate = format_configs(raw, pretty=pretty)
        assert '"first\r\nsecond"' in candidate
        assert "'a\\'b'" in candidate
        assert format_configs(candidate, pretty=pretty) == candidate


def test_other_jinja_comments_raw_blocks_and_whitespace_controls_unchanged():
    before = "-- header\n{# {{ config(a=1) }} #}\n{% raw %}{{ config(a=1) }}{% endraw %}\n"
    after = "\n{{ ref('orders') }} {{ custom({'x':1}) }} {{- config(a=1) -}}"
    assert format_configs(before + COMPACT + after) == before + PRETTY + after


def test_parenthesized_config_is_preserved_as_unsupported():
    raw = "{{ (config(meta={'x': [1]})) }}"
    assert format_configs(raw) == raw
    assert format_configs(raw, pretty=False) == raw


def test_multiple_configs_and_crlf_headers():
    code = "-- header\r\n" + COMPACT + "\r\n-- between\r\n{{ config(tags=['sales']) }}"
    candidate = format_configs(code)
    assert candidate.startswith("-- header\r\n" + PRETTY + "\r\n-- between\r\n")
    assert validate_template(candidate) == validate_template(code)
    assert format_configs(candidate) == candidate


@pytest.mark.parametrize("pretty", [True, False])
def test_source_optimizer_formats_only_config_jinja(pretty):
    code = "-- authored header\n" + COMPACT + "\nselect o.id from {{ ref('orders') }} o"
    candidate = optimize_source(code, "duckdb", pretty=pretty)
    assert candidate.startswith("-- authored header\n" + (PRETTY if pretty else COMPACT))
    assert "{{ ref('orders') }}" in candidate
    assert optimize_source(candidate, "duckdb", pretty=pretty) == candidate


@pytest.mark.parametrize("mode, expected", [("pretty", PRETTY), ("compact", COMPACT)])
def test_optimize_cli_preview_apply_and_idempotence(native, mode, expected):
    path = put(native, "models/config_format.sql", COMPACT + "\nselect 1 as id")
    before = snapshot(native)
    preview = invoke(native, "optimize", "-s", "config_format", "--format", mode, "--preview")
    assert preview.exit_code == 0, preview.output
    assert snapshot(native) == before
    result = invoke(native, "optimize", "-s", "config_format", "--format", mode)
    assert result.exit_code == 0, result.output
    assert path.read_text(encoding="utf-8").startswith(expected + "\n\n")
    after = snapshot(native)
    again = invoke(native, "optimize", "-s", "config_format", "--format", mode)
    assert again.exit_code == 0, again.output
    assert snapshot(native) == after
