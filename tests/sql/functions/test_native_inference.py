"""Fixed native return families extend shared inference without changing ASTs."""

import pytest
from sqlglot import Dialect, exp, parse_one
from sqlglot.optimizer.annotate_types import annotate_types

from dbt_extra.analysis.type_inference import inferred_types
from dbt_extra.sql.functions import FunctionSpec, function_spec
from dbt_extra.sql.parser import parse_authored
from tests.sql.functions.helpers import enrichment


CASES = [
    ("snowflake", "is_array(parse_json('[]'))", "BOOLEAN"),
    ("redshift", "soundex('hello')", "VARCHAR"),
    ("redshift", "json_extract_path_text('{}', 'a')", "VARCHAR"),
    ("redshift", "json_extract_path_text('{}', 'a', 'b', true)", "VARCHAR"),
    ("trino", "current_timezone()", "VARCHAR"),
]


@pytest.mark.parametrize("dialect,expression,returns", CASES)
def test_native_return_family_and_nested_inference(dialect, expression, returns):
    tree = parse_authored(f"SELECT {expression} AS result", dialect).tree
    node = tree.selects[0].this
    assert not isinstance(node, exp.Anonymous) and function_spec(node) is None
    before = tree.dump()
    metadata = dict(Dialect.get_or_raise(dialect).EXPRESSION_METADATA)
    baseline = annotate_types(tree.copy(), dialect=dialect).dump()
    for settings in (dialect, dialect + ", normalization_strategy=case_sensitive"):
        assert inferred_types(tree, {}, settings) == {"result": returns}
        nested = parse_authored(f"SELECT COALESCE({expression}, NULL) AS result", settings).tree
        assert inferred_types(nested, {}, settings) == {"result": returns}
        scoped = parse_authored(f"SELECT q.result FROM (SELECT {expression} AS result) q", settings).tree
        assert inferred_types(scoped, {}, settings) == {"result": returns}
    assert tree.dump() == before
    assert type(tree.selects[0].this) is type(parse_one(expression, read=dialect))
    assert Dialect.get_or_raise(dialect).EXPRESSION_METADATA == metadata
    assert annotate_types(tree.copy(), dialect=dialect).dump() == baseline


@pytest.mark.parametrize("dialect,expression,returns", CASES)
def test_native_inference_enrichment(native, dialect, expression, returns):
    # The shared enrichment contract is reusable; this record is never registered.
    enrichment(native, dialect, FunctionSpec("native_example", expression, returns, 0, 0))


@pytest.mark.parametrize("dialect,expression", [
    ("databricks", "try_add(1, 2)"),
    ("duckdb", "list_transform([1,2], lambda x: x + 1)"),
    ("fabric", "json_value('{}', '$.a')"),
    ("spark", "is_array(id)"),
])
def test_input_dependent_and_other_dialect_types_stay_unresolved(dialect, expression):
    tree = parse_authored(f"SELECT {expression} AS result FROM t", dialect).tree
    assert inferred_types(tree, {"t": {"id": "BIGINT"}}, dialect) == {}
