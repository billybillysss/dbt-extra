"""Authored rewrites: bindings first, conservative evidence, reversible rendering."""

from collections import Counter
import json

import duckdb
import pytest
from sqlglot import exp

from dbt_extra.errors import SpecError
from dbt_extra.optimization import optimize, optimize_source
from dbt_extra.project.project import Project
from dbt_extra.sql.macros import StaticMacros, parse_model
from dbt_extra.sql.parser import parse_authored
from dbt_extra.sql.schema_evidence import SourceSchemas
from dbt_extra.sql.shorthand import output_spans
from dbt_extra.sql.source_rules import collapse_complementary_union, decorrelate_filter_exists, short_names
from tests.helpers import invoke, project, put, snapshot


SCHEMA = {
    "violations": {"id": "INT", "type_id": "INT", "amount": "INT"},
    "types": {"id": "INT", "code": "VARCHAR"},
}
RENAMED = """with violation as (
    select v.id as violation_id, v.type_id as violation_type_id from violations v
), violation_type as (
    select vt.id, vt.code as violation_type_code from types vt
)
select v.violation_id, v.violation_type_id, vt.violation_type_code
from violation v join violation_type vt on v.violation_type_id = vt.id"""


def result(connection, code, *, ordered=False):
    cursor = connection.execute(code)
    names = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    return names, [str(d[1]) for d in cursor.description], rows if ordered else Counter(rows)


QUERIES = [
    RENAMED,
    "with x as (select * from violations) select x.id, t.code from x join types t on x.type_id=t.id",
    "with x as (select v.* from violations v) select x.id, t.code from x left join types t on x.type_id=t.id",
    "with x as (select v.id, v.type_id, v.amount from violations v) select a.id, b.amount from x a join x b on a.type_id=b.type_id where b.amount>1",
    "with x as (select v.id, v.amount from violations v where v.type_id>0) select x.id from x where x.amount>1",
    "with x as (select count(*) as n from violations v where v.amount>999) select 1 as marker from x",
    "with x as (select count(*) as n from violations v) select x.n from x",
    "select v.id from violations v union all select t.id from types t",
    "select v.type_id, count(*) as n from violations v group by 1 having count(*)>0 order by 2, 1",
    "with x as (select v.id, row_number() over(partition by v.type_id order by v.amount, v.id) as rn from violations v) select x.id from x where x.rn=1",
    "select v.id, row_number() over(order by v.id) as rn from violations v qualify rn=1",
    "select distinct v.type_id from violations v order by 1 nulls last limit 2 offset 1",
    "with x as (select v.id from violations v) select q.id from (with x as (select t.id from types t) select x.id from x) q join x on q.id=x.id",
    "select v.id from violations v left join types t on v.type_id=t.id and t.code='A' where t.code is null",
    "select v.id from violations v right join types t on v.type_id=t.id where v.id is null",
    "select v.id, t.code from violations v full join types t on v.type_id=t.id",
    "select v.id from violations v where date '2026-01-01' + v.amount > date '2026-01-02' order by v.id nulls last",
    "select v.id from violations v where exists(select 1 from types t where t.id=v.type_id)",
    "select v.id from violations v where exists(select 1 from types t where t.id=v.type_id and t.code='A')",
    "select v.id from violations v where exists(select 1 from types t where v.type_id=t.id and t.code is null)",
    "select v.id from violations v where exists(select 1 from types t where t.id=v.type_id) and v.amount>1",
    "select v.id, v.amount from violations v where v.amount=2 union all "
    "select v.id, v.amount from violations v where v.amount<>2",
    "select v.id, v.amount from violations v where v.amount<>2 union all "
    "select v.id, v.amount from violations v where v.amount=2",
    "select v.id from violations v where (v.type_id=1 and v.amount>1) or v.type_id=2",
    "select q.id from (select distinct v.id, v.type_id from violations v) q where q.type_id>1 and true",
    "select a.id, b.id as peer, c.id as matched from violations a cross join violations b "
    "join violations c on a.type_id=c.type_id and b.type_id=c.type_id",
    "select a.id, a.n, b.n as other from "
    "(select v.id, count(*) as n from violations v group by v.id) a join "
    "(select v.id, count(*) as n from violations v group by v.id) b on a.id=b.id",
    "with x as (select v.id, v.amount, v.type_id as unused, "
    "row_number() over(order by v.amount, v.id) as rn from violations v) "
    "select x.id, x.rn from x where x.rn<=2 order by x.rn limit 2",
    "with x as (select v.id, v.type_id, v.amount as unused from violations v) "
    "select q.type_id from (select distinct x.id, x.type_id from x) q",
]


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("code", QUERIES)
def test_results_labels_duplicates_nulls_empty_and_order(code, empty):
    with duckdb.connect() as con:
        con.execute("create table violations(id integer, type_id integer, amount integer)")
        con.execute("create table types(id integer, code varchar)")
        if not empty:
            con.execute("insert into violations values (1,1,2),(1,1,2),(2,2,null),(3,null,0),(4,9,3)")
            con.execute("insert into types values (1,'A'),(1,'A'),(2,null),(5,'B')")
        candidate = optimize_source(code, "duckdb", schema=SCHEMA)
        ordered = bool(parse_authored(code, "duckdb").tree.args.get("order"))
        assert result(con, candidate, ordered=ordered) == result(con, code, ordered=ordered)
        assert optimize_source(candidate, "duckdb", schema=SCHEMA) == candidate


@pytest.mark.parametrize("dialect", ["duckdb", "postgres", "snowflake", "bigquery", "spark", "tsql"])
def test_renamed_cte_ast_bindings_and_six_dialects(dialect):
    candidate = optimize_source(RENAMED, dialect)
    tree = parse_authored(candidate, dialect).tree
    bindings = {p.output_name.lower(): (p.this.table, p.this.name) for p in tree.selects}
    assert bindings == {"violation_id": ("v", "id"), "violation_type_id": ("v", "type_id"),
                        "violation_type_code": ("vt", "code")}
    assert optimize_source(candidate, dialect) == candidate


@pytest.mark.parametrize("code", [
    "select * from violations v join types t on v.type_id=t.id",
    "select v.* from violations v join types t on v.type_id=t.id",
    "select id from violations v join types t on v.type_id=t.id",
    "select id from violations v join types t using(id)",
    "select id from violations v natural join types t",
    "with x as (select * from violations) select x.id from x",
])
def test_unknown_join_and_projection_star_are_actionable_skips(code):
    with pytest.raises(SpecError, match="schema"):
        optimize_source(code, "duckdb")


def test_explicit_bindings_unknown_inputs_and_count_star_are_not_rejected():
    assert "v.id" in optimize_source("select v.id from violations v join types t on v.type_id=t.id", "duckdb")
    assert "COUNT(*)" in optimize_source("select count(*) from violations", "duckdb")


def test_partial_schema_unknown_is_not_column_absence():
    with pytest.raises(SpecError, match="unknown joined schema"):
        optimize_source("select id from violations v join types t on v.type_id=t.id", "duckdb",
                        schema={"violations": SCHEMA["violations"]})
    with pytest.raises(SpecError):
        optimize_source("select v.not_a_column from violations v", "duckdb", schema=SCHEMA)


def test_ordered_star_expansion_and_modifiers():
    schema = {"t": {"z": "INT", "a": "INT", '"Case"': "INT"}}
    code = 'with x as (select * from t) select x.* exclude(a) from x'
    candidate = optimize_source(code, "duckdb", schema=schema)
    assert [p.output_name for p in parse_authored(candidate, "duckdb").tree.selects] == ["z", "Case"]
    assert not any(p.is_star for p in parse_authored(candidate, "duckdb").tree.selects)


def test_star_replacement_preserves_results_and_aliases():
    code = "select * replace (b + 1 as b) from t"
    candidate = optimize_source(code, "duckdb", schema={"t": {"a": "INT", "b": "INT"}})
    with duckdb.connect() as con:
        con.execute("create table t(a integer, b integer)")
        con.execute("insert into t values (1, 2), (1, 2), (null, null)")
        assert result(con, code) == result(con, candidate)


@pytest.mark.parametrize("code", [
    "select * rename (b as Renamed) from t", "select * ilike 'a%' from t",
])
def test_unrestorable_or_unsupported_star_modifiers_skip(code):
    with pytest.raises(SpecError, match="Unsupported projection star modifier"):
        optimize_source(code, "snowflake", schema={"t": {"a": "INT", "b": "INT"}})


@pytest.mark.parametrize("code", [
    "select * from t x join t y on x.a=y.a", "select x.a as Foo, x.b as foo from t x",
])
def test_expanded_or_normalized_duplicate_outputs_skip(code):
    with pytest.raises(SpecError, match="Duplicate output names"):
        optimize_source(code, "duckdb", schema={"t": {"a": "INT", "b": "INT"}})


@pytest.mark.parametrize("code", [
    "select v.id, v.id from violations v",
    "select x.id from violations x where not exists(select 1 from types y where y.id=x.type_id)",
    "with recursive x as (select 1 as id union all select id+1 from x where id<3) select id from x",
    "select random() as n", "select custom_udf(id) as n from violations", "select from (",
])
def test_duplicate_correlated_recursive_volatile_unknown_malformed_skip(code):
    with pytest.raises(SpecError):
        optimize_source(code, "duckdb", schema=SCHEMA)


@pytest.mark.parametrize("code, aliases", [
    ("select a.col1 as col1 from t a", []),
    ('select a."Case" as "Case" from t a', []),
    ('select a.foo as "FOO" from t a', ["FOO"]),
    ('select a.Foo as foo from t a', ["foo"]),
    ('select a.foo as "foo" from t a', ["foo"]),
])
def test_redundant_aliases_only_when_exact_case_and_quoting_match(code, aliases):
    candidate = optimize_source(code, "duckdb")
    assert [a.alias for a in parse_authored(candidate, "duckdb").tree.find_all(exp.Alias)] == aliases
    with duckdb.connect() as con:
        con.execute('create table t(col1 integer, "Case" integer, Foo integer)')
        assert result(con, code) == result(con, candidate)


def test_preserves_authored_spelling_names_comments_and_config():
    code = "{{ config(materialized='view') }}\n-- explanation\nselect T.UpperCase as OutputName from MyTable T"
    candidate = optimize_source(code, "duckdb")
    assert "T.UpperCase AS OutputName" in candidate and "MyTable AS T" in candidate
    assert candidate.count("{{ config(materialized='view') }}") == 1
    assert "explanation" in candidate
    assert optimize_source(candidate, "duckdb") == candidate


def test_unnamed_expression_label_is_not_replaced_with_synthetic_name():
    candidate = optimize_source("select v.id+2 from violations v", "duckdb")
    assert "_col_" not in candidate
    with duckdb.connect() as con:
        con.execute("create table violations(id integer)")
        assert result(con, candidate) == result(con, "select v.id+2 from violations v")


def test_unnamed_outputs_are_reported_as_formatting_only(native):
    put(native, "models/unnamed.sql", "select o.amount+2 from {{ ref('orders') }} o")
    changes, skipped = optimize(project(native), select=["unnamed"])
    assert not skipped
    assert changes.optimization_report["model.shop.unnamed"]["formatting_only"]


def test_short_names_skip_authored_names_and_cross_z_without_rewriting_text():
    names = short_names()
    assert [next(names) for _ in range(28)] == [chr(97 + i) for i in range(26)] + ["aa", "ab"]
    candidate = optimize_source("select foo.id, a.code from foo join types a on foo.type_id=a.id", "duckdb")
    assert "foo AS b" in candidate and "types AS a" in candidate and "b.id" in candidate
    assert "extra_input" not in candidate and "_q_" not in candidate
    tables = [f"table_{i}" for i in range(28)]
    code = "select " + ", ".join(f"{t}.id as out_{i}" for i, t in enumerate(tables)) + " from " + " cross join ".join(tables)
    tree = parse_authored(optimize_source(code, "duckdb"), "duckdb").tree
    expected = {chr(97+i) for i in range(26)} | {"aa", "ab"}
    assert {t.alias for t in tree.find_all(exp.Table)} == expected
    # Join ordering may change, but generated aliases must still bind each output
    # to the original table rather than changing out_0 ... out_27's meaning.
    relations = {t.alias: t.name for t in tree.find_all(exp.Table)}
    assert [relations[p.this.table] for p in tree.selects] == tables


def test_macro_pruning_tracks_hidden_dependency_and_exact_call_counts(native):
    put(native, "macros/value.sql", "{% macro twice(value) %}{{ value }} + {{ value }}{% endmacro %}")
    call = "{{ twice('x.amount') }}"
    code = "with x as (select o.id, o.amount from {{ ref('orders') }} o) select " + call + " as total, " + call + " as other from x"
    path = put(native, "models/fct_inspection.sql", code)
    before = snapshot(native)
    changes, skipped = optimize(project(native), select=["fct_inspection"])
    assert not skipped
    candidate = changes.after[path].decode()
    assert candidate.count(call) == 2 and "WITH x AS" in candidate
    assert "o.amount" in candidate and "extra_macro_" not in candidate
    assert "o.id" not in candidate
    assert changes.optimization_report["model.shop.fct_inspection"]["status"] == "rewritten"
    changes.apply(preview=True)
    assert snapshot(native) == before
    changes.apply()
    assert not optimize(project(native), select=["fct_inspection"])[0].changed()


@pytest.mark.parametrize("body", [
    "id, amount", "*", "{{ adapter.get_columns_in_relation('x') }}", "{{ env_var('TOKEN') }}",
    "{{ run_query('select 1') }}", "{{ var('columns') }}", "random()", "unknown_udf(amount)",
])
def test_macro_fragments_context_and_volatile_calls_skip_without_inlining(native, body):
    put(native, "macros/value.sql", "{% macro fields() %}" + body + "{% endmacro %}")
    path = put(native, "models/unsafe.sql", "select {{ fields() }} from {{ ref('orders') }}")
    changes, skipped = optimize(project(native), select=["unsafe", "revenue"])
    assert "model.shop.unsafe" in skipped and path not in changes.after
    assert "--expand" not in skipped["model.shop.unsafe"]
    assert "model.shop.revenue" in changes.optimization_report


@pytest.mark.parametrize("expression, expected", [
    ("value.upper()", "ABC"), ("value.lower()", "abc"), ("value.trim()", "AbC"),
    ("value | upper | trim", "ABC"), ("value | lower | trim", "abc"),
    ("false and missing", "False"), ("true or missing", "True"),
    ("1 < 2 and 'a' != 'b'", "True"),
])
def test_bounded_static_allowlist_extensions(native, expression, expected):
    put(native, "macros/value.sql", "{% macro value(value) %}{{ " + expression + " }}{% endmacro %}")
    call = next(output_spans("{{ value(' AbC ') }}"))[3]
    assert StaticMacros(project(native)).call(call).strip() == expected


def test_flat_tuple_unpack_loop_and_comparison(native):
    body = "{% macro pairs() %}{% for field, kind in [('id','int'),('amount','number')] %}{% if kind == 'int' or kind == 'number' %}{{ field | upper }}{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}{% endmacro %}"
    put(native, "macros/value.sql", body)
    parsed = parse_model(project(native), "select {{ pairs() }} from {{ ref('orders') }}", expand=True)
    assert [p.output_name for p in parsed.tree.selects] == ["ID", "AMOUNT"]


@pytest.mark.parametrize("body", [
    "{{ value.upper(1) }}", "{{ value | trim('x') }}", "{{ 1 == '1' }}", "{{ value.__class__ }}",
    "{% for a,b in [(1,)] %}{{ a }}{% endfor %}",
    "{% for (a,(b,c)) in [(1,(2,3))] %}{{ a }}{% endfor %}",
])
def test_interpreter_still_rejects_unapproved_operations(native, body):
    put(native, "macros/value.sql", "{% macro value(value) %}" + body + "{% endmacro %}")
    with pytest.raises(SpecError):
        parse_model(project(native), "select {{ value('id') }} as n", expand=True)


def test_project_local_complete_outputs_not_documentation_are_schema_evidence(native):
    put(native, "models/int_inspection_premise_violation_history.sql", "select o.id as inspection_job_id, o.amount as violation_id from {{ ref('orders') }} o")
    path = put(native, "models/int_inspection_premise_violation_event.sql", "select h.* from {{ ref('int_inspection_premise_violation_history') }} h join {{ ref('orders') }} o on h.inspection_job_id=o.id")
    p = project(native)
    changes, skipped = optimize(p, select=["int_inspection_premise_violation_event"])
    assert not skipped
    candidate = changes.after[path].decode()
    assert "inspection_job_id" in candidate and "violation_id" in candidate and "*" not in candidate
    resource = p.resources["model.shop.int_inspection_premise_violation_history"]
    evidence = SourceSchemas(p).for_resource(resource)
    assert evidence.complete and [c.name for c in evidence.columns] == ["inspection_job_id", "violation_id"]
    assert evidence.resource_id == resource.id and evidence.freshness == "operation snapshot"


def test_documented_source_and_curated_downstream_columns_are_partial(native):
    path = put(native, "models/documented.sql", "select * from {{ source('raw', 'orders') }}")
    put(native, "models/curated.yml", "version: 2\nmodels:\n- name: documented\n  columns:\n  - name: id\n")
    changes, skipped = optimize(project(native), select=["documented"])
    assert "complete ordered input schemas" in skipped["model.shop.documented"]
    assert path not in changes.after


def test_schema_dependency_cycles_skip_per_model(native):
    put(native, "models/a.sql", "select b.id from {{ ref('b') }} b")
    put(native, "models/b.sql", "select a.id from {{ ref('a') }} a")
    changes, skipped = optimize(project(native), select=["a", "revenue"])
    assert "Schema dependency cycle" in skipped["model.shop.a"]
    assert "model.shop.revenue" in changes.optimization_report


@pytest.mark.parametrize("filename", ["models/slv/orders.sql", "macros/value.sql", "models/schema.yml", "dbt_project.yml", "target/manifest.json"])
def test_entire_inference_read_set_conflicts_even_noop(native, filename):
    put(native, "macros/value.sql", "{% macro value(v) %}{{ v }}{% endmacro %}")
    changes, skipped = optimize(project(native), select=["revenue"])
    assert not skipped
    changes.apply()
    changes, skipped = optimize(project(native), select=["revenue"])
    assert not skipped and not changes.changed()
    path = native / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((path.read_bytes() if path.exists() else b"") + b"\n")
    with pytest.raises(SpecError, match="Conflict"):
        changes.apply()


def test_optimizer_keyerror_is_chained_actionable_and_batch_continues(native, monkeypatch):
    from dbt_extra import optimization
    real = optimization.rewrite_source

    def broken(tree, dialect):
        if any(c.name == "broken_column" for c in tree.find_all(exp.Column)):
            raise KeyError("inspection_job_id")
        return real(tree, dialect)

    monkeypatch.setattr(optimization, "rewrite_source", broken)
    with pytest.raises(SpecError, match="KeyError.*inspection_job_id") as caught:
        optimize_source("select a.broken_column from t a", "duckdb")
    assert isinstance(caught.value.__cause__, KeyError)
    path = put(native, "models/broken.sql", "select a.broken_column from t a")
    changes, skipped = optimize(project(native), select=["broken", "revenue"])
    assert "model.shop.broken" in skipped and path not in changes.after
    assert "model.shop.revenue" in changes.optimization_report


def test_fixed_point_cycle_and_nonconvergence_skip(monkeypatch):
    from dbt_extra import optimization
    monkeypatch.setattr(optimization, "_once", lambda code, *a, **k: "b" if code == "a" else "a")
    with pytest.raises(SpecError, match="cycle"):
        optimize_source("a", "duckdb")
    monkeypatch.setattr(optimization, "_once", lambda code, *a, **k: code + " ")
    with pytest.raises(SpecError, match="four passes"):
        optimize_source("a", "duckdb")


def test_unrelated_programming_keyerrors_are_not_swallowed(monkeypatch):
    from dbt_extra import optimization

    def broken_parser(*args, **kwargs):
        raise KeyError("programming error outside optimizer")

    monkeypatch.setattr(optimization, "parse_authored", broken_parser)
    with pytest.raises(KeyError, match="programming error outside optimizer"):
        optimize_source("select t.id from t", "duckdb")


def test_fabricspark_autodetection_and_explicit_precedence(native):
    put(native, "target/manifest.json", json.dumps({"metadata": {"project_name": "shop", "adapter_type": "fabricspark"}}))
    assert Project(native).require_dialect() == "spark"
    assert Project(native, dialect="duckdb").require_dialect() == "duckdb"
    put(native, "extra_project.yaml", "version: 2\nanalysis:\n  dialect: postgres\n")
    assert Project(native).require_dialect() == "postgres"


def test_cli_preview_reports_accepted_proposed_and_written_separately(native):
    before = snapshot(native)
    response = invoke(native, "optimize", "-s", "revenue", "--preview")
    assert response.exit_code == 0, response.output
    assert "1 accepted" in response.output and "1 proposed SQL change(s)" in response.output
    assert "SQL files written: 0" in response.output
    assert snapshot(native) == before


@pytest.mark.parametrize("code,status", [
    ("SELECT\n  o.id\nFROM {{ ref('orders') }} AS o;", "unchanged"),
    ("select distinct o.id from {{ ref('orders') }} o", "formatted"),
    ("select distinct id from {{ ref('orders') }}", "qualified"),
    ("select o.id, 1+2 as n from {{ ref('orders') }} o", "rewritten"),
])
def test_change_classification_uses_original_to_fixed_point_ast(native, code, status):
    path = put(native, "models/classification.sql", code)
    if status == "unchanged":
        # Use actual canonical bytes (including platform-independent newlines).
        canonical = optimize(project(native), select=["classification"])[0].after[path]
        path.write_bytes(canonical)
        code = canonical.decode()
    changes, skipped = optimize(project(native), select=["classification"])
    assert not skipped
    report = changes.optimization_report["model.shop.classification"]
    assert report == {"status": status, "formatting_only": status == "formatted",
                      "changed": status != "unchanged", "retained": (
                          ["DISTINCT tuple retained to preserve row multiplicity."]
                          if "distinct" in code else [])}
    if status == "unchanged":
        assert not changes.changed()
        changes.apply()
        assert path.read_bytes() == code.encode()


def test_cli_reports_formatting_without_claiming_structural_rewrites(native):
    path = put(native, "models/format_only.sql", "select distinct o.id from {{ ref('orders') }} o")
    before = snapshot(native)
    response = invoke(native, "optimize", "-s", "format_only", "--preview")
    assert response.exit_code == 0, response.output
    assert "0 structurally rewritten, 0 qualified, 1 formatting-only, 0 unchanged" in response.output
    assert "1 proposed SQL change(s)" in response.output
    assert "SQL files written: 0" in response.output
    assert snapshot(native) == before
    changes, skipped = optimize(project(native), select=["format_only"])
    assert not skipped and path in changes.changed()
    response = invoke(native, "optimize", "-s", "format_only")
    assert response.exit_code == 0 and "SQL files written: 1" in response.output
    assert path.read_bytes() == changes.after[path]
    second, _ = optimize(project(native), select=["format_only"])
    assert second.optimization_report["model.shop.format_only"]["status"] == "unchanged"


MACRO_QUERIES = [
    # Multiple consumers jointly require both columns, including hidden strings.
    "with x as (select o.id, o.amount from {{ ref('orders') }} o) "
    "select {{ twice('a.amount') }} as total, b.id from x a join x b on a.id=b.id",
    # Dropping id changes DISTINCT multiplicity even though only amount is read.
    "with x as (select distinct o.id, o.amount from {{ ref('orders') }} o) "
    "select {{ twice('x.amount') }} as total from x",
    # A global aggregate still returns one row on empty input.
    "with x as (select 1 as marker, count(*) as n from {{ ref('orders') }} o) "
    "select {{ twice('x.marker') }} as total from x",
    # Positional ORDER BY must not shift after pruning an earlier projection.
    "with x as (select o.id, o.amount from {{ ref('orders') }} o order by 2, 1 limit 2) "
    "select {{ twice('x.amount') }} as total from x",
    "with x as (select o.id, o.amount from {{ ref('orders') }} o group by 1, 2) "
    "select {{ twice('x.amount') }} as total from x",
    # GROUP/ORDER BY ALL implicitly depend on the complete authored projection.
    "with x as (select o.id, o.amount from {{ ref('orders') }} o group by all) "
    "select {{ twice('x.amount') }} as total from x",
    "with x as (select o.id, o.amount from {{ ref('orders') }} o order by all limit 2) "
    "select {{ twice('x.amount') }} as total from x",
    # CTE column alias lists must keep their positional interface.
    "with x(key, value) as (select o.id, o.amount from {{ ref('orders') }} o) "
    "select {{ twice('x.value') }} as total from x",
    # QUALIFY and window ordering retain their nonselected dependencies.
    "with x as (select o.id, o.amount, row_number() over(order by o.amount, o.id) as rn "
    "from {{ ref('orders') }} o qualify rn<=2) select {{ twice('x.amount') }} as total from x",
    # A macro projection is preserved even when the consumer does not read it.
    "with x as (select o.id, {{ twice('o.amount') }} as unused from {{ ref('orders') }} o) "
    "select x.id from x",
    # GROUP BY / HAVING dependencies survive dead aggregate pruning.
    "with x as (select o.id, sum(o.amount) as total, max(o.amount) as unused "
    "from {{ ref('orders') }} o group by o.id having sum(o.amount)>1) "
    "select {{ twice('x.total') }} as total from x",
    # Qualification can inline local aliases; authored pruning must not drop them.
    "with x as (select o.amount as value, value+1 as total from {{ ref('orders') }} o) "
    "select {{ twice('x.total') }} as total from x",
    # A scalar subquery inside a macro prevents one-to-one scope mapping.
    "select {{ twice('(select max(o.amount) from orders o)') }} as total",
]


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("code", MACRO_QUERIES)
def test_macro_pruning_preserves_rows_and_barrier_dependencies(native, code, empty):
    put(native, "macros/value.sql", "{% macro twice(value) %}{{ value }} + {{ value }}{% endmacro %}")
    path = put(native, "models/macro_safety.sql", code)
    p = project(native)
    changes, skipped = optimize(p, select=["macro_safety"])
    assert not skipped
    candidate = changes.after[path].decode()
    from dbt_extra.sql.macros import macro_calls
    assert Counter(raw for _, _, raw, _ in macro_calls(code)) == Counter(
        raw for _, _, raw, _ in macro_calls(candidate))

    def executable(text):
        parsed = parse_model(p, text, expand=True)
        for table in parsed.tree.find_all(exp.Table):
            if table.name in parsed.refs:
                table.set("this", exp.to_identifier("orders"))
        return parsed.tree.sql(dialect="duckdb")

    with duckdb.connect() as con:
        con.execute("create table orders(id integer, amount integer)")
        if not empty:
            con.execute("insert into orders values (1,2),(1,2),(2,2),(3,null),(null,4),(4,0)")
        assert result(con, executable(code)) == result(con, executable(candidate))
    changes.apply()
    second, skipped = optimize(project(native), select=["macro_safety"])
    assert not skipped and not second.changed()


SOURCE_RULES = {
    "normalize": "select v.id from violations v where (v.id=1 and v.amount>1) or v.id=2",
    "pushdown": "select q.id from (select distinct v.id from violations v) q where q.id>1 and true",
    "join": "select a.id, b.id as peer, c.id as matched from violations a cross join violations b "
            "join violations c on a.type_id=c.type_id and b.type_id=c.type_id",
    "factor": "select a.id, a.n, b.n as other from "
              "(select v.id, count(*) as n from violations v group by v.id) a join "
              "(select v.id, count(*) as n from violations v group by v.id) b on a.id=b.id",
    "membership": "select v.id from violations v where exists("
                  "select 1 from types t where t.id=v.type_id and t.code='A')",
    "union": "select v.id from violations v where v.amount=2 union all "
             "select v.id from violations v where v.amount<>2",
}


@pytest.mark.parametrize("dialect", ["duckdb", "postgres", "snowflake", "bigquery", "spark", "tsql"])
@pytest.mark.parametrize("rule", SOURCE_RULES)
def test_guarded_source_rules_rewrite_roundtrip_and_converge(rule, dialect):
    code = SOURCE_RULES[rule]
    candidate = optimize_source(code, dialect, schema=SCHEMA)
    tree = parse_authored(candidate, dialect).tree
    if rule == "normalize":
        assert isinstance(tree.args["where"].this, exp.And)
    elif rule == "pushdown":
        assert tree.args.get("where") is None
        assert next(tree.find_all(exp.Subquery)).this.args.get("where")
    elif rule == "join":
        assert len(list(tree.find_all(exp.Join))) == 2
        assert not any(j.kind == "CROSS" for j in tree.find_all(exp.Join))
    elif rule == "factor":
        assert len(list(tree.find_all(exp.CTE))) == 1
        assert len(list(tree.find_all(exp.Select))) == 2
    elif rule == "membership":
        assert not list(tree.find_all(exp.Exists))
        assert len(list(tree.find_all(exp.In))) == 1
    else:
        assert not list(tree.find_all(exp.Union))
        assert len(list(tree.find_all(exp.Table))) == 1
        assert tree.args.get("where")
    assert optimize_source(candidate, dialect, schema=SCHEMA) == candidate


@pytest.mark.parametrize("term", [
    "not exists(select 1 from types t where t.id=v.type_id)",
    "exists(select 1 from types t where t.id=v.type_id) or v.id=1",
    "exists(select 1 from types t where t.id>v.type_id)",
    "exists(select 1 from types t where t.id=v.type_id and t.id=v.id)",
    "exists(select 1 from types t where t.id=v.type_id limit 1)",
    "exists(select count(*) from types t where t.id=v.type_id)",
    "exists(select 1 from types t where t.id=v.type_id or t.code='A')",
    "exists(select 1 from types t where t.id=v.type_id -- keep comment\n)",
])
def test_decorrelation_does_not_generalize_beyond_positive_equality_filters(term):
    code = "select v.id from violations v where " + term
    tree = parse_authored(code, "duckdb").tree
    assert decorrelate_filter_exists(tree.copy()) == tree
    with pytest.raises(SpecError, match="Correlated"):
        optimize_source(code, "duckdb", schema=SCHEMA)


@pytest.mark.parametrize("code", [
    "select exists(select 1 from types t where t.id=v.type_id) as eligible from violations v",
    "select v.id from violations v where exists(select 1 from types t where t.id=t.id)",
    "select v.id from violations v where exists(select 1 from types t where t.id=id)",
])
def test_decorrelation_keeps_output_truth_values_and_unknown_bindings(code):
    tree = parse_authored(code, "duckdb").tree
    assert decorrelate_filter_exists(tree.copy()) == tree


@pytest.mark.parametrize("left,right,operator", [
    ("select v.id from violations v where v.amount=2", "select v.id from violations v where v.amount<>2", "UNION"),
    ("select distinct v.id from violations v where v.amount=2", "select distinct v.id from violations v where v.amount<>2", "UNION ALL"),
    ("select v.id from violations v where v.amount=2", "select v.amount from violations v where v.amount<>2", "UNION ALL"),
    ("select v.id from violations v where v.amount=2", "select v.id from violations v where v.amount<>3", "UNION ALL"),
    ("select v.id from violations v where v.amount=null", "select v.id from violations v where v.amount<>null", "UNION ALL"),
    ("select v.id from violations v where v.amount=2 and v.id>0", "select v.id from violations v where v.amount<>2", "UNION ALL"),
    ("select v.id from violations v where v.amount=2 limit 1", "select v.id from violations v where v.amount<>2 limit 1", "UNION ALL"),
])
def test_union_collapse_requires_identical_bag_producing_inputs(left, right, operator):
    code = f"({left}) {operator} ({right})" if "limit" in left else f"{left} {operator} {right}"
    tree = parse_authored(code, "duckdb").tree
    assert collapse_complementary_union(tree.copy()) == tree


def test_projection_pruning_without_macros_keeps_lateral_aliases_and_shared_consumers():
    code = ("with x as (select v.id, v.amount as value, value+1 as total from violations v) "
            "select a.total, b.id from x a join x b on a.id=b.id")
    candidate = optimize_source(code, "duckdb", schema=SCHEMA)
    with duckdb.connect() as con:
        con.execute("create table violations(id integer, type_id integer, amount integer)")
        con.execute("insert into violations values (1,1,2),(1,1,2),(2,null,null)")
        assert result(con, candidate) == result(con, code)


def test_union_collapse_keeps_comparison_coercions_not_just_null_checks():
    code = ("select v.id from violations v where v.amount='not-a-number' union all "
            "select v.id from violations v where v.amount<>'not-a-number'")
    candidate = optimize_source(code, "duckdb", schema=SCHEMA)
    with duckdb.connect() as con:
        con.execute("create table violations(id integer, type_id integer, amount integer)")
        con.execute("insert into violations values (1,1,2)")
        for value in (code, candidate):
            with pytest.raises(duckdb.ConversionException):
                con.execute(value).fetchall()


@pytest.mark.parametrize("kind,remove", [
    ("INT", True), ("BIGINT", True), ("SMALLINT", False),
    ("DECIMAL(12,2)", False), ("DOUBLE", False), ("UNKNOWN", False),
])
def test_zero_identity_requires_exact_known_duckdb_input_type(kind, remove):
    code = "select t.amount+0 as amount from t"
    candidate = optimize_source(code, "duckdb", schema={"t": {"amount": kind}})
    assert bool(parse_authored(candidate, "duckdb").tree.find(exp.Add)) is not remove
    with duckdb.connect() as con:
        con.execute(f"create table t(amount {kind if kind != 'UNKNOWN' else 'DECIMAL(12,2)'})")
        con.execute("insert into t values (null),(0),(1),(1),(-1)")
        if kind in {"INT", "BIGINT"}:
            lo, hi = (-2147483648, 2147483647) if kind == "INT" else (-9223372036854775808, 9223372036854775807)
            con.execute("insert into t values (?), (?)", [lo, hi])
        assert result(con, candidate) == result(con, code)
    assert optimize_source(candidate, "duckdb", schema={"t": {"amount": kind}}) == candidate


@pytest.mark.parametrize("expression", [
    "1.00+2.00", "1.00*2.00", "1.00-2.00", "100/100",
    "cast(1 as smallint)+0", "t.amount+0", "t.amount*1", "t.amount-0",
    "coalesce(null, 1.00+2.00)", "case when t.amount>0 then 1.00+2.00 else 0 end",
])
@pytest.mark.parametrize("empty", [False, True])
def test_numeric_simplification_preserves_exact_types_scales_and_rows(expression, empty):
    code = f"select {expression} as value from t"
    schema = {"t": {"amount": "DECIMAL(12,2)"}}
    candidate = optimize_source(code, "duckdb", schema=schema)
    with duckdb.connect() as con:
        con.execute("create table t(amount decimal(12,2))")
        if not empty:
            con.execute("insert into t values (null),(0),(1.23),(1.23),(-1.23),(9999999999.99)")
        assert result(con, code) == result(con, candidate)
    assert optimize_source(candidate, "duckdb", schema=schema) == candidate


@pytest.mark.parametrize("code", [
    "select 2147483647+1 as n from t",
    "select 2147483647*2 as n from t",
    "select t.amount from t where cast('not-a-number' as int)=1",
    "select t.amount from t where 'not-a-number'=1",
])
def test_local_simplification_does_not_erase_overflow_or_conversion_errors(code):
    candidate = optimize_source(code, "duckdb", schema={"t": {"amount": "INT"}})
    with duckdb.connect() as con:
        con.execute("create table t(amount int)")
        con.execute("insert into t values (1)")
        for text in (code, candidate):
            with pytest.raises((duckdb.OutOfRangeException, duckdb.ConversionException)):
                con.execute(text).fetchall()


def test_arithmetic_in_predicates_is_not_given_to_unrestricted_simplification():
    code = "select t.amount from t where 2147483647+1 > 0"
    candidate = optimize_source(code, "duckdb", schema={"t": {"amount": "INT"}})
    assert parse_authored(candidate, "duckdb").tree.args["where"].find(exp.Add)


@pytest.mark.parametrize("code", [
    "select 1+2 as n, count(*) as total from violations v where true",
    "select 1+2 as n, row_number() over(order by v.id) as rn from violations v where true limit 2",
    "select distinct v.id, 1+2 as n from violations v where v.id>0 and true",
    "select v.id, 1+2 as n from violations v left join types t on v.type_id=t.id where true",
    "select 1+2 as n from violations union all select 2+1 as n from types",
])
def test_local_simplification_is_not_disabled_by_unrelated_query_barriers(code):
    candidate = optimize_source(code, "duckdb", schema=SCHEMA)
    tree = parse_authored(candidate, "duckdb").tree
    assert not tree.find(exp.Add)
    assert not any(w.this == exp.true() or w.this.find(exp.Boolean) for w in tree.find_all(exp.Where))
    with duckdb.connect() as con:
        con.execute("create table violations(id int, type_id int, amount int)")
        con.execute("create table types(id int, code varchar)")
        for empty in (True, False):
            if not empty:
                con.execute("insert into violations values (1,1,2),(1,1,2),(2,null,null)")
                con.execute("insert into types values (1,'A'),(1,'A')")
            assert result(con, code) == result(con, candidate)
    assert optimize_source(candidate, "duckdb", schema=SCHEMA) == candidate


@pytest.mark.parametrize("clause", ["order by 1+2", "group by 1+2"])
def test_local_constant_folding_never_creates_positional_clause_bindings(clause):
    code = "select count(*) as n from violations v " + clause
    candidate = optimize_source(code, "duckdb", schema=SCHEMA)
    assert parse_authored(candidate, "duckdb").tree.find(exp.Add)


def test_decimal_literal_typing_dialect_is_not_assumed_to_be_fixed_width_integer():
    candidate = optimize_source("select 1+2 as n", "snowflake")
    assert parse_authored(candidate, "snowflake").tree.find(exp.Add)


@pytest.mark.parametrize("dialect", ["duckdb", "postgres", "spark", "tsql", "bigquery"])
def test_fixed_width_constant_rules_fold_only_within_proven_integer_bounds(dialect):
    code = ("select 1+2 as small, 2147483646+1 as edge, 2147483647+1 as overflow, "
            "1.00+2.00 as decimal_value, 1-2 as negative")
    candidate = optimize_source(code, dialect)
    expressions = {p.alias: p.this for p in parse_authored(candidate, dialect).tree.selects}
    assert expressions["small"] == exp.Literal.number(3)
    assert expressions["edge"] == exp.Literal.number(2147483647)
    assert isinstance(expressions["overflow"], exp.Add)
    assert isinstance(expressions["decimal_value"], exp.Add)
    assert isinstance(expressions["negative"], exp.Sub)
    assert optimize_source(candidate, dialect) == candidate


@pytest.mark.parametrize("dialect", ["postgres", "snowflake", "spark", "tsql", "bigquery"])
def test_zero_identity_is_not_assumed_safe_in_other_dialects(dialect):
    candidate = optimize_source("select t.amount+0 as amount from t", dialect, schema={"t": {"amount": "INT"}})
    assert parse_authored(candidate, dialect).tree.find(exp.Add)


def test_macro_local_simplification_preserves_calls_hidden_dependencies_and_scopes(native):
    put(native, "macros/value.sql", "{% macro twice(value) %}{{ value }} + {{ value }}{% endmacro %}")
    call = "{{ twice('x.amount') }}"
    code = ("with x as (select o.id as unused, o.amount from {{ ref('orders') }} o where true) "
            "select " + call + " as total, " + call + "+0 as unchanged, 1+2 as n, "
            "row_number() over(order by x.amount) as rn from x where x.amount>0 and true limit 2")
    path = put(native, "models/local_macro.sql", code)
    p = project(native)
    before = snapshot(native)
    changes, skipped = optimize(p, select=["local_macro"])
    assert not skipped
    candidate = changes.after[path].decode()
    assert snapshot(native) == before
    assert candidate.count(call) == 2 and "unused" not in candidate
    assert "3 AS n" in candidate and "TRUE" not in candidate
    authored = parse_model(p, candidate).tree
    assert len(list(authored.find_all(exp.Select))) == 2
    assert authored.find(exp.Window) and authored.args["limit"]
    assert authored.find(exp.Add).this.name in parse_model(p, candidate).macros
    for text in (code, candidate):
        assert "x.amount" in parse_model(p, text, expand=True).tree.sql()
    with duckdb.connect() as con:
        con.execute("create table orders(id int, amount decimal(12,2))")
        con.execute("insert into orders values (1,1.23),(1,1.23),(2,null),(3,0)")

        def executable(text):
            parsed = parse_model(p, text, expand=True)
            for table in parsed.tree.find_all(exp.Table):
                if table.name in parsed.refs:
                    table.set("this", exp.to_identifier("orders"))
            return parsed.tree.sql(dialect="duckdb")

        assert result(con, executable(code), ordered=True) == result(con, executable(candidate), ordered=True)
    changes.apply()
    assert not optimize(project(native), select=["local_macro"])[0].changed()


def test_boolean_coercions_and_commented_expressions_are_not_erased():
    code = "select 1 and true as b, 1 /* keep */ + 2 as n"
    candidate = optimize_source(code, "duckdb")
    assert "keep" in candidate
    assert parse_authored(candidate, "duckdb").tree.find(exp.Add)
    with duckdb.connect() as con:
        assert result(con, code) == result(con, candidate)


def test_preview_explains_retained_arithmetic_and_distinct(native):
    put(native, "models/retained.sql", "select q.amount from (select distinct o.id, o.amount+0 as amount "
        "from {{ ref('orders') }} o) q")
    before = snapshot(native)
    response = invoke(native, "optimize", "-s", "retained", "--preview")
    assert response.exit_code == 0, response.output
    assert "Arithmetic identity retained" in response.output
    assert "DISTINCT tuple retained" in response.output
    assert snapshot(native) == before
