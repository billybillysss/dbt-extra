"""Catalog registration and extension boundaries, independent of real new catalogs."""

from dataclasses import replace

import pytest
from sqlglot import exp, parse_one

from dbt_extra.analysis.type_inference import inferred_types
from dbt_extra.sql.functions import (
    CATALOG, FunctionSpec, FunctionShape, function_barrier, function_shape,
    function_spec, has_generators, recognize_functions,
)
from dbt_extra.sql.functions.registry import _catalog
from dbt_extra.sql.rewrites.structural import plain_queries
from dbt_extra.sql.parser import parse_authored


SPEC = FunctionSpec("example", "example()", "INT", 0, 0)


@pytest.mark.parametrize("duplicate", [SPEC, replace(SPEC, name="EXAMPLE")])
def test_duplicate_source_entries_fail_before_dictionary_construction(duplicate):
    with pytest.raises(ValueError, match="Duplicate function name: example"):
        _catalog([SPEC, duplicate])


@pytest.mark.parametrize("changes,reason", [
    ({"name": "EXAMPLE"}, "lowercase"),
    ({"minimum": -1}, "arity"),
    ({"minimum": 2, "maximum": 1}, "arity"),
    ({"kind": "scaler"}, "kind"),
    ({"volatility": "deterministic"}, "volatility"),
    ({"arities": ()}, "arities"),
    ({"arities": (0, 0)}, "arities"),
    ({"arities": (1, 0)}, "arities"),
    ({"arities": (-1, 0)}, "arities"),
    ({"arities": (0, 1)}, "arities"),
])
def test_invalid_registration_is_rejected(changes, reason):
    with pytest.raises(ValueError, match=reason):
        _catalog([replace(SPEC, **changes)])


def test_registration_retains_every_valid_entry():
    variadic = replace(SPEC, name="variadic", minimum=1, maximum=None)
    assert _catalog([SPEC, variadic]) == {"example": SPEC, "variadic": variadic}


@pytest.mark.parametrize("dialect,name,expression", [
    ("spark", "future_generator", "future_generator()"),
    ("spark", "future_generator", "future_generator(array(named_struct('a', 1)))"),
    ("tsql", "json_tuple", "json_tuple('{}', 'a')"),
    ("tsql", "inline_outer", "inline_outer(items)"),
    ("tsql", "window", "window(ts, '1 minute')"),
    ("tsql", "session_window", "session_window(ts, '1 minute')"),
    ("spark", "string_split", "string_split('a,b', ',')"),
])
def test_unhandled_generators_never_inherit_name_based_shape(monkeypatch, dialect, name, expression):
    # A real registration needs a dialect-specific shape rule. Even a familiar
    # name or literal struct array is not proof of output width/cardinality.
    spec = FunctionSpec(name, expression, None, 0, None, kind="generator")
    monkeypatch.setitem(CATALOG[dialect], name, spec)
    tree = parse_authored("SELECT " + expression + " AS result", dialect).tree
    node = tree.selects[0].this
    assert function_spec(node) == spec
    assert function_shape(node) == FunctionShape("generator", None, "unknown")
    assert function_barrier(node)
    assert has_generators(tree)
    assert not plain_queries(tree, aggregates=True)
    assert inferred_types(tree, {}, dialect) == {}


@pytest.mark.parametrize("dialect,expression,expected", [
    ("spark, normalization_strategy=case_sensitive", "isnull(1)", "BOOLEAN"),
    ("tsql, version=16", "isjson('{}')", "INTEGER"),
    ("fabric, version=16", "isjson('{}')", "INT"),
    ("databricks, version=16", "isnull(1)", "BOOLEAN"),
    ("duckdb, normalization_strategy=case_sensitive", "pg_typeof(1)", "TEXT"),
    ("postgres, normalization_strategy=case_sensitive", "pg_backend_pid()", "INT"),
    ("snowflake, normalization_strategy=case_sensitive", "last_query_id()", "VARCHAR"),
    ("bigquery, normalization_strategy=case_sensitive", "error('stop')", None),
    ("redshift, normalization_strategy=case_sensitive", "fnv_hash('abc')", "BIGINT"),
    ("trino, normalization_strategy=case_sensitive", "human_readable_seconds(1)", "VARCHAR"),
    ("athena, normalization_strategy=case_sensitive", "invoker_principal()", "VARCHAR"),
])
def test_settings_select_base_catalog_without_replacing_authored_dialect(dialect, expression, expected):
    tree = parse_authored("SELECT " + expression + " AS result", dialect).tree
    before = tree.dump()
    node = tree.selects[0].this
    raw = parse_one(expression, read=dialect)
    assert function_spec(raw) is None
    assert function_spec(raw, dialect) == function_spec(node)
    assert function_spec(node) is not None
    assert node.meta["extra_function_dialect"] == dialect
    assert node.copy().meta["extra_function_dialect"] == dialect
    assert inferred_types(tree, {}, dialect) == ({"result": expected} if expected else {})
    assert tree.dump() == before
    assert isinstance(raw, exp.Anonymous)


def test_settings_are_retained_by_native_type_inference():
    dialect = "spark, normalization_strategy=case_sensitive"
    tree = parse_authored("SELECT isnull(t.MixedID) AS local, ABS(t.MixedID) AS native FROM t", dialect).tree
    schema = {"t": {"MixedID": "BIGINT", "mixedid": "STRING"}}
    assert inferred_types(tree, schema, dialect) == {"local": "BOOLEAN", "native": "BIGINT"}


@pytest.mark.parametrize("dialect,expression", [
    ("databricks, version=16", "arrays_overlap(array(1), array(2))"),
    ("fabric, version=16", "xact_state()"),
    ("duckdb, normalization_strategy=case_sensitive", "isjson('{}')"),
    ("athena, normalization_strategy=case_sensitive", "human_readable_seconds(1)"),
    ("trino, normalization_strategy=case_sensitive", "invoker_principal()"),
    ("redshift, normalization_strategy=case_sensitive", "pg_backend_pid()"),
])
def test_settings_do_not_introduce_related_dialect_inheritance(dialect, expression):
    tree = recognize_functions(parse_one("SELECT " + expression, read=dialect), dialect)
    assert function_spec(tree.selects[0]) is None


def test_explicit_dialect_overrides_annotation_without_mutating_it():
    node = parse_authored("SELECT xact_state()", "tsql, version=16").tree.selects[0]
    assert function_spec(node) is not None
    assert function_spec(node, "fabric, version=16") is None
    assert function_shape(node, "fabric, version=16") == FunctionShape("unknown", None, "unknown")
    assert node.meta["extra_function_dialect"] == "tsql, version=16"


def test_settings_use_the_same_explicit_generator_dispatch():
    node = parse_authored("SELECT json_tuple('{}', 'a', 'b')", "spark, version=3.5").tree.selects[0]
    assert function_shape(node) == FunctionShape("generator", 2, "one_per_row")


@pytest.mark.parametrize("dialect,expression,expected", [
    ("fabric", "isjson('{}', OBJECT)", "INT"),
    ("databricks", "schema_of_json('{}', map('allowComments', 'true'))", "STRING"),
    ("postgres", "current_setting('search_path', true)", "TEXT"),
    ("postgres", "jsonb_path_exists('{}'::jsonb, '$.a', '{}'::jsonb)", "BOOLEAN"),
    ("postgres", "jsonb_path_exists('{}'::jsonb, '$.a', '{}'::jsonb, true)", "BOOLEAN"),
    ("snowflake", "get_ddl('TABLE', 't', true)", "VARCHAR"),
    ("snowflake", "last_query_id(-2)", "VARCHAR"),
    ("redshift", "fnv_hash('abc', 1)", "BIGINT"),
    ("trino", "bar(0.5, 10, rgb(255, 0, 0), rgb(0, 255, 0))", "VARCHAR"),
])
def test_audited_optional_arguments_keep_recognition_and_type(dialect, expression, expected):
    tree = parse_authored("SELECT " + expression + " AS result", dialect).tree
    before = tree.dump()
    assert function_spec(tree.selects[0].this) is not None
    assert inferred_types(tree, {}, dialect) == {
        "result": exp.DataType.build(expected, dialect=dialect).sql(dialect=dialect)}
    assert tree.dump() == before


@pytest.mark.parametrize("dialect,expression", [
    ("fabric", "string_split('a,b', ',', 1)"),
    ("fabric", "xact_state()"),
    ("fabric", "datalength('abc')"),
    ("databricks", "arrays_overlap(array(1), array(2))"),
    ("duckdb", "getenv('HOME')"),
    ("duckdb", "current_setting('threads', true)"),
    ("postgres", "stats(id)"),
    ("trino", "bar(0.5, 10, rgb(255, 0, 0))"),
    ("athena", "human_readable_seconds(3600)"),
    ("redshift", "pg_backend_pid()"),
])
def test_deferred_or_other_dialect_calls_stay_unregistered(dialect, expression):
    tree = parse_authored("SELECT " + expression + " AS result FROM t", dialect).tree
    assert function_spec(tree.selects[0].this) is None
    assert inferred_types(tree, {"t": {"id": "BIGINT"}}, dialect) == {}


def test_shared_function_names_keep_dialect_specific_policies():
    for dialect, expected in (("duckdb", {"result": "TEXT"}), ("postgres", {})):
        tree = parse_authored("SELECT pg_typeof(1) AS result", dialect).tree
        assert function_spec(tree.selects[0].this) is not None
        assert inferred_types(tree, {}, dialect) == expected
    for dialect, expected in (("duckdb", {}), ("postgres", {"result": "TEXT"})):
        tree = parse_authored("SELECT current_setting('threads') AS result", dialect).tree
        assert inferred_types(tree, {}, dialect) == expected


@pytest.mark.parametrize("dialect,expression", [
    ("fabric", "json_value('{}', '$.a')"),
    ("databricks", "try_add(1, 2)"),
    ("databricks", "count_if(true)"),
    ("duckdb", "list_transform([1,2], lambda x: x + 1)"),
    ("postgres", "generate_series(1, 3)"),
    ("snowflake", "is_array(parse_json('[]'))"),
    ("bigquery", "json_strip_nulls(JSON '{}')"),
    ("redshift", "soundex('hello')"),
    ("trino", "current_timezone()"),
    ("athena", "typeof(1)"),
])
def test_native_nodes_are_not_replaced_by_new_catalog_entries(dialect, expression):
    raw = parse_one(expression, read=dialect)
    assert not isinstance(raw, exp.Anonymous)
    tree = parse_authored("SELECT " + expression, dialect).tree
    assert type(tree.selects[0]) is type(raw)
    assert function_spec(tree.selects[0]) is None


def test_disjoint_overload_is_rechecked_after_ast_edits():
    node = parse_authored("SELECT bar(0.5, 10)", "trino").tree.selects[0]
    assert function_spec(node).arities == (2, 4)
    node.append("expressions", exp.Literal.number(1))
    assert function_spec(node) is None
    assert function_shape(node) == FunctionShape("unknown", None, "unknown")
    assert function_barrier(node)


def test_bigquery_range_array_is_one_scalar_value_even_with_optional_flag():
    tree = parse_authored("SELECT generate_range_array(RANGE(DATE '2020-01-01', DATE '2020-02-01'), INTERVAL 1 DAY, false) AS result", "bigquery").tree
    before = tree.dump()
    assert function_spec(tree.selects[0].this) is not None
    assert function_shape(tree.selects[0].this) == FunctionShape("scalar", 1, "one_per_row")
    assert not has_generators(tree)
    assert inferred_types(tree, {}, "bigquery") == {}
    assert tree.dump() == before
